"""
nova.project.detector
~~~~~~~~~~~~~~~~~~~~~
Detects the active project's root, languages, frameworks, and git status
without making any external network calls or spawning subprocesses unsafely.
"""
from __future__ import annotations

import logging
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from nova.project.context import LanguageInfo

logger = logging.getLogger("nova.project.detector")

# ------------------------------------------------------------------ #
# Constants                                                            #
# ------------------------------------------------------------------ #

# Files whose presence signals a project root
_ROOT_MARKERS = {
    ".git", "package.json", "pyproject.toml", "Cargo.toml",
    "pom.xml", "go.mod", "composer.json", "requirements.txt",
    "Makefile", "CMakeLists.txt", ".hg", "setup.py", "setup.cfg",
}

# Extension → language name
_EXT_TO_LANG: Dict[str, str] = {
    ".py":    "Python",
    ".ts":    "TypeScript",
    ".tsx":   "TypeScript",
    ".js":    "JavaScript",
    ".jsx":   "JavaScript",
    ".mjs":   "JavaScript",
    ".rs":    "Rust",
    ".go":    "Go",
    ".java":  "Java",
    ".kt":    "Kotlin",
    ".cs":    "C#",
    ".cpp":   "C++",
    ".cc":    "C++",
    ".cxx":   "C++",
    ".c":     "C",
    ".h":     "C",
    ".rb":    "Ruby",
    ".php":   "PHP",
    ".swift": "Swift",
    ".scala": "Scala",
    ".hs":    "Haskell",
    ".lua":   "Lua",
    ".r":     "R",
    ".jl":    "Julia",
    ".dart":  "Dart",
    ".ex":    "Elixir",
    ".exs":   "Elixir",
    ".sh":    "Shell",
    ".bash":  "Shell",
}

# Framework signatures: list of (file_or_dir_name, framework_label)
_FRAMEWORK_SIGNALS: List[Tuple[str, str]] = [
    # JavaScript / TypeScript
    ("next.config.js",       "Next.js"),
    ("next.config.ts",       "Next.js"),
    ("nuxt.config.ts",       "Nuxt.js"),
    ("nuxt.config.js",       "Nuxt.js"),
    ("svelte.config.js",     "Svelte"),
    ("svelte.config.ts",     "Svelte"),
    ("astro.config.mjs",     "Astro"),
    ("vite.config.ts",       "Vite"),
    ("vite.config.js",       "Vite"),
    ("remix.config.js",      "Remix"),
    ("angular.json",         "Angular"),
    ("ember-cli-build.js",   "Ember.js"),
    # Python
    ("manage.py",            "Django"),
    ("wsgi.py",              "Django"),
    ("asgi.py",              "Django/ASGI"),
    ("flask_app.py",         "Flask"),
    ("app.py",               "Flask"),       # heuristic; checked against deps
    ("main.py",              "FastAPI"),     # heuristic
    ("alembic.ini",          "SQLAlchemy"),
    # Rust
    ("Rocket.toml",          "Rocket"),
    # Java
    ("pom.xml",              "Maven"),
    ("build.gradle",         "Gradle"),
    ("build.gradle.kts",     "Gradle"),
    # Ruby
    ("Gemfile",              "Ruby on Rails"),
    # PHP
    ("artisan",              "Laravel"),
    # Mobile
    ("pubspec.yaml",         "Flutter"),
    ("build.gradle",         "Android"),
    ("Podfile",              "iOS/CocoaPods"),
]


# ------------------------------------------------------------------ #
# Root detection                                                        #
# ------------------------------------------------------------------ #

def find_project_root(start: Path) -> Path:
    """
    Walk upward from `start` until a root marker is found.
    Falls back to `start` if no marker is detected within 10 levels.
    """
    current = start.resolve()
    for _ in range(10):
        for marker in _ROOT_MARKERS:
            if (current / marker).exists():
                logger.debug(f"Project root detected at: {current} (marker: {marker})")
                return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    logger.debug(f"No root marker found; using start dir: {start}")
    return start.resolve()


# ------------------------------------------------------------------ #
# Language detection                                                    #
# ------------------------------------------------------------------ #

def detect_languages(file_paths: List[str]) -> List[LanguageInfo]:
    """
    Analyse a list of relative file paths (from the indexer) and return
    LanguageInfo objects ranked by file count, most dominant first.
    """
    lang_counter: Counter = Counter()
    ext_counter: Counter = Counter()

    for path_str in file_paths:
        ext = Path(path_str).suffix.lower()
        lang = _EXT_TO_LANG.get(ext)
        if lang:
            lang_counter[lang] += 1
            ext_counter[(lang, ext)] += 1

    if not lang_counter:
        return []

    total = sum(lang_counter.values())
    most_common_lang = lang_counter.most_common(1)[0][0]

    results: List[LanguageInfo] = []
    for lang, count in lang_counter.most_common():
        # Pick the most frequent extension for this language
        dominant_ext = max(
            (ext for (l, ext) in ext_counter if l == lang),
            key=lambda e: ext_counter[(lang, e)],
            default="",
        )
        results.append(LanguageInfo(
            name=lang,
            extension=dominant_ext,
            file_count=count,
            primary=(lang == most_common_lang),
        ))

    return results


# ------------------------------------------------------------------ #
# Framework detection                                                   #
# ------------------------------------------------------------------ #

def detect_frameworks(
    root: Path,
    file_paths: List[str],
    dependencies: Dict[str, str],
) -> List[str]:
    """
    Detect frameworks by looking for signal files and known dependency names.
    """
    frameworks: List[str] = []
    file_set = set(file_paths)
    dep_names = {k.lower() for k in dependencies}

    # File-presence signals
    for signal_file, label in _FRAMEWORK_SIGNALS:
        # Check directly in root
        if (root / signal_file).exists() or signal_file in file_set:
            if label not in frameworks:
                frameworks.append(label)

    # Dependency-name signals
    dep_signals: List[Tuple[str, str]] = [
        ("react",        "React"),
        ("vue",          "Vue.js"),
        ("angular",      "@angular/core"),
        ("svelte",       "Svelte"),
        ("nextjs",       "Next.js"),
        ("fastapi",      "FastAPI"),
        ("flask",        "Flask"),
        ("django",       "Django"),
        ("express",      "Express.js"),
        ("nestjs",       "NestJS"),
        ("spring-boot",  "Spring Boot"),
        ("gin",          "Gin (Go)"),
        ("actix-web",    "Actix (Rust)"),
        ("rocket",       "Rocket (Rust)"),
        ("rails",        "Ruby on Rails"),
        ("laravel",      "Laravel"),
    ]
    for dep_key, label in dep_signals:
        if dep_key in dep_names and label not in frameworks:
            frameworks.append(label)

    # Refine ambiguous Flask/FastAPI: check actual deps
    if "Flask" in frameworks and "flask" not in dep_names:
        frameworks.remove("Flask")
    if "FastAPI" in frameworks and "fastapi" not in dep_names:
        frameworks.remove("FastAPI")

    return frameworks


# ------------------------------------------------------------------ #
# Git detection                                                         #
# ------------------------------------------------------------------ #

def detect_git(root: Path) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Returns (is_git_repo, current_branch, remote_url).
    Uses only safe, read-only git commands. Falls back gracefully.
    """
    git_dir = root / ".git"
    if not git_dir.exists():
        return False, None, None

    branch: Optional[str] = None
    remote: Optional[str] = None

    try:
        # Read HEAD directly to avoid spawning git in environments without it
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        m = re.match(r"^ref: refs/heads/(.+)$", head)
        branch = m.group(1) if m else "detached"
    except Exception as e:
        logger.debug(f"Cannot read git HEAD: {e}")

    try:
        config_path = git_dir / "config"
        if config_path.exists():
            config = config_path.read_text(encoding="utf-8")
            m = re.search(r'url\s*=\s*(.+)', config)
            remote = m.group(1).strip() if m else None
    except Exception as e:
        logger.debug(f"Cannot read git config: {e}")

    return True, branch, remote


# ------------------------------------------------------------------ #
# Project name                                                          #
# ------------------------------------------------------------------ #

def detect_project_name(root: Path, manifest_metadata: Dict[str, str]) -> str:
    """
    Returns the project name from manifest or falls back to directory name.
    """
    return (
        manifest_metadata.get("name")
        or root.name
    ).strip() or root.name
