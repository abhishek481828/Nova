"""
nova.project.indexer
~~~~~~~~~~~~~~~~~~~~
Async filesystem indexer. Walks the project tree and builds an in-memory
dict[relative_path → FileNode]. Uses asyncio.to_thread to avoid blocking.
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Dict, List, Set

from nova.project.context import FileNode

logger = logging.getLogger("nova.project.indexer")

# ------------------------------------------------------------------ #
# Configuration                                                         #
# ------------------------------------------------------------------ #

IGNORED_DIRS: Set[str] = {
    "node_modules", ".git", "dist", "build", "target",
    "__pycache__", ".venv", ".pytest_cache", ".mypy_cache",
    ".tox", "venv", "env", ".eggs", "*.egg-info",
    ".idea", ".vscode", ".DS_Store", "coverage",
    ".next", ".nuxt", ".svelte-kit", "out",
}

IGNORED_EXTENSIONS: Set[str] = {
    ".pyc", ".pyo", ".pyd", ".class", ".o", ".so", ".dll",
    ".exe", ".bin", ".db", ".sqlite", ".sqlite3",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".ogg", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".lock",  # package-lock.json, yarn.lock, etc. — tracked separately
}

# Max single-file size to index (skip huge generated files)
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB

# ------------------------------------------------------------------ #
# Import extractors                                                     #
# ------------------------------------------------------------------ #

_PY_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)", re.MULTILINE
)
_JS_IMPORT_RE = re.compile(
    r"""(?:import|require)\s*\(?['"]([^'"]+)['"]\)?""", re.MULTILINE
)
_RUST_USE_RE = re.compile(r"^\s*use\s+([\w:]+)", re.MULTILINE)
_GO_IMPORT_RE = re.compile(r'"([^"]+)"')


def _extract_imports(path: Path, content: str) -> tuple:
    ext = path.suffix.lower()
    try:
        if ext == ".py":
            matches = _PY_IMPORT_RE.findall(content)
            return tuple(m[0] or m[1] for m in matches if m[0] or m[1])
        elif ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
            return tuple(set(_JS_IMPORT_RE.findall(content)[:50]))
        elif ext == ".rs":
            return tuple(set(_RUST_USE_RE.findall(content)[:50]))
        elif ext == ".go":
            return tuple(set(_GO_IMPORT_RE.findall(content)[:50]))
    except Exception:
        pass
    return ()


# ------------------------------------------------------------------ #
# Core indexing logic (sync, runs in thread)                           #
# ------------------------------------------------------------------ #

def _should_ignore_dir(name: str) -> bool:
    return name in IGNORED_DIRS or name.endswith(".egg-info")


def _index_sync(root: Path) -> Dict[str, FileNode]:
    """
    Synchronous walk — intended to be called via asyncio.to_thread.
    Returns a dict of relative_path → FileNode.
    """
    index: Dict[str, FileNode] = {}

    try:
        for entry in _walk(root):
            try:
                rel = str(entry.relative_to(root))
                stat = entry.stat()
                size = stat.st_size
                mtime = stat.st_mtime

                if size > MAX_FILE_SIZE:
                    continue

                ext = entry.suffix.lower()
                if ext in IGNORED_EXTENSIONS:
                    continue

                imports: tuple = ()
                # Only parse source files for imports
                if ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".rs", ".go"):
                    try:
                        content = entry.read_text(encoding="utf-8", errors="replace")
                        imports = _extract_imports(entry, content)
                    except Exception:
                        pass

                index[rel] = FileNode(
                    path=rel,
                    extension=ext,
                    size_bytes=size,
                    mtime=mtime,
                    imports=imports,
                )
            except Exception as e:
                logger.debug(f"Skipping {entry}: {e}")
    except Exception as e:
        logger.error(f"Index walk failed: {e}")

    return index


def _walk(root: Path):
    """Depth-first directory walk, honouring IGNORED_DIRS."""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            for child in sorted(current.iterdir()):
                if child.is_dir():
                    if not _should_ignore_dir(child.name):
                        stack.append(child)
                elif child.is_file():
                    yield child
        except PermissionError:
            continue


# ------------------------------------------------------------------ #
# Public async API                                                      #
# ------------------------------------------------------------------ #

async def build_index(root: Path) -> Dict[str, FileNode]:
    """
    Asynchronously build the file index for *root*.
    Offloads the synchronous walk to a thread pool worker.
    """
    logger.info(f"Building project index for: {root}")
    index = await asyncio.to_thread(_index_sync, root)
    logger.info(f"Index complete — {len(index)} files indexed under {root}")
    return index


def build_index_sync(root: Path) -> Dict[str, FileNode]:
    """
    Synchronous wrapper for callers that cannot use async (e.g. daemon thread).
    """
    return _index_sync(root)


def update_index_for_file(
    index: Dict[str, FileNode],
    root: Path,
    path: Path,
) -> Dict[str, FileNode]:
    """
    Incrementally update the index for a single changed/added file.
    Call with the mutable index dict; returns the same dict.
    """
    try:
        rel = str(path.relative_to(root))
        if not path.exists():
            index.pop(rel, None)
            return index

        stat = path.stat()
        ext = path.suffix.lower()
        imports: tuple = ()
        if ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".rs", ".go"):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                imports = _extract_imports(path, content)
            except Exception:
                pass

        index[rel] = FileNode(
            path=rel,
            extension=ext,
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
            imports=imports,
        )
    except Exception as e:
        logger.debug(f"Failed to update index for {path}: {e}")
    return index
