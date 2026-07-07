"""
nova.project.manifest
~~~~~~~~~~~~~~~~~~~~~
Parsers for common dependency manifest files.
Each parser returns a dict with at minimum:
  - dependencies: Dict[str, str]
  - dev_dependencies: Dict[str, str]
  - metadata: Dict[str, Any]
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("nova.project.manifest")

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.debug(f"Cannot read {path}: {e}")
        return ""


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug(f"Cannot parse JSON {path}: {e}")
        return {}


# ------------------------------------------------------------------ #
# package.json (Node.js / npm / yarn / pnpm)                          #
# ------------------------------------------------------------------ #

def parse_package_json(path: Path) -> Dict[str, Any]:
    data = _read_json(path)
    return {
        "name": data.get("name", ""),
        "version": data.get("version", ""),
        "description": data.get("description", ""),
        "scripts": data.get("scripts", {}),
        "dependencies": data.get("dependencies", {}),
        "dev_dependencies": data.get("devDependencies", {}),
        "metadata": {
            "engines": data.get("engines", {}),
            "main": data.get("main", ""),
            "type": data.get("type", ""),
        },
    }


# ------------------------------------------------------------------ #
# requirements.txt (Python pip)                                        #
# ------------------------------------------------------------------ #

_REQ_LINE = re.compile(
    r"^\s*([A-Za-z0-9_.\-]+)\s*([><=!~^]{1,3}\s*[\w.*]+)?\s*$"
)

def parse_requirements_txt(path: Path) -> Dict[str, Any]:
    deps: Dict[str, str] = {}
    for line in _read_text(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = _REQ_LINE.match(line)
        if m:
            name = m.group(1)
            version = (m.group(2) or "").strip()
            deps[name] = version
    return {"dependencies": deps, "dev_dependencies": {}, "metadata": {}}


# ------------------------------------------------------------------ #
# pyproject.toml (PEP 517/518/621)                                     #
# ------------------------------------------------------------------ #

def parse_pyproject_toml(path: Path) -> Dict[str, Any]:
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # backport
        except ImportError:
            logger.debug("tomllib/tomli not available; falling back to regex for pyproject.toml")
            return _parse_pyproject_regex(path)

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug(f"Cannot parse pyproject.toml: {e}")
        return {"dependencies": {}, "dev_dependencies": {}, "metadata": {}}

    project = data.get("project", {})
    deps_raw: List[str] = project.get("dependencies", [])
    deps = _parse_pep508_list(deps_raw)

    # Also try poetry style
    tool = data.get("tool", {})
    poetry = tool.get("poetry", {})
    if poetry:
        deps.update(_flatten_poetry_deps(poetry.get("dependencies", {})))

    return {
        "name": project.get("name", poetry.get("name", "")),
        "version": project.get("version", poetry.get("version", "")),
        "dependencies": deps,
        "dev_dependencies": _flatten_poetry_deps(
            poetry.get("dev-dependencies", {})
        ),
        "metadata": {"description": project.get("description", "")},
    }


def _parse_pyproject_regex(path: Path) -> Dict[str, Any]:
    """Minimal regex fallback when tomllib is not available."""
    text = _read_text(path)
    name_m = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return {
        "name": name_m.group(1) if name_m else "",
        "dependencies": {},
        "dev_dependencies": {},
        "metadata": {},
    }


def _parse_pep508_list(deps: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for dep in deps:
        m = re.match(r"^([A-Za-z0-9_.\-]+)(.*)", dep.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _flatten_poetry_deps(deps: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in deps.items():
        if k.lower() == "python":
            continue
        out[k] = str(v) if not isinstance(v, dict) else v.get("version", "")
    return out


# ------------------------------------------------------------------ #
# Cargo.toml (Rust)                                                    #
# ------------------------------------------------------------------ #

def parse_cargo_toml(path: Path) -> Dict[str, Any]:
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return {"dependencies": {}, "dev_dependencies": {}, "metadata": {}}

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"dependencies": {}, "dev_dependencies": {}, "metadata": {}}

    pkg = data.get("package", {})
    raw_deps = data.get("dependencies", {})
    deps = {k: (str(v) if not isinstance(v, dict) else v.get("version", ""))
            for k, v in raw_deps.items()}
    return {
        "name": pkg.get("name", ""),
        "version": pkg.get("version", ""),
        "dependencies": deps,
        "dev_dependencies": {},
        "metadata": {"edition": pkg.get("edition", "")},
    }


# ------------------------------------------------------------------ #
# pom.xml (Maven / Java)                                               #
# ------------------------------------------------------------------ #

def parse_pom_xml(path: Path) -> Dict[str, Any]:
    text = _read_text(path)
    if not text:
        return {"dependencies": {}, "dev_dependencies": {}, "metadata": {}}

    name_m = re.search(r"<artifactId>([^<]+)</artifactId>", text)
    version_m = re.search(r"<version>([^<]+)</version>", text)

    deps: Dict[str, str] = {}
    for m in re.finditer(
        r"<dependency>.*?<groupId>([^<]+)</groupId>.*?<artifactId>([^<]+)</artifactId>"
        r"(?:.*?<version>([^<]+)</version>)?",
        text, re.DOTALL
    ):
        key = f"{m.group(1)}:{m.group(2)}"
        deps[key] = m.group(3) or ""

    return {
        "name": name_m.group(1) if name_m else "",
        "version": version_m.group(1) if version_m else "",
        "dependencies": deps,
        "dev_dependencies": {},
        "metadata": {},
    }


# ------------------------------------------------------------------ #
# composer.json (PHP)                                                  #
# ------------------------------------------------------------------ #

def parse_composer_json(path: Path) -> Dict[str, Any]:
    data = _read_json(path)
    return {
        "name": data.get("name", ""),
        "version": data.get("version", ""),
        "dependencies": data.get("require", {}),
        "dev_dependencies": data.get("require-dev", {}),
        "metadata": {"description": data.get("description", "")},
    }


# ------------------------------------------------------------------ #
# Dispatcher                                                           #
# ------------------------------------------------------------------ #

MANIFEST_PARSERS = {
    "package.json": parse_package_json,
    "requirements.txt": parse_requirements_txt,
    "pyproject.toml": parse_pyproject_toml,
    "Cargo.toml": parse_cargo_toml,
    "pom.xml": parse_pom_xml,
    "composer.json": parse_composer_json,
}


def parse_manifest(path: Path) -> Dict[str, Any]:
    """Parse any recognised manifest file; returns empty dicts on failure."""
    parser = MANIFEST_PARSERS.get(path.name)
    if parser is None:
        return {"dependencies": {}, "dev_dependencies": {}, "metadata": {}}
    try:
        return parser(path)
    except Exception as e:
        logger.warning(f"Manifest parse error for {path}: {e}")
        return {"dependencies": {}, "dev_dependencies": {}, "metadata": {}}
