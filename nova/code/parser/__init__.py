"""
nova.code.parser
~~~~~~~~~~~~~~~~
Parser registry. Dispatches to the correct language parser by file extension.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from nova.code.parser.base import ParseResult, Symbol
from nova.code.parser.python_parser import parse_python
from nova.code.parser.typescript_parser import parse_typescript
from nova.code.parser.generic_parser import parse_generic

logger = logging.getLogger("nova.code.parser")

# Extensions handled by the Python AST parser
_PYTHON_EXTS = {".py", ".pyi"}

# Extensions handled by the TypeScript/JS regex parser
_TS_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}

# Extensions handled by the generic regex parser
_GENERIC_EXTS = {
    ".rs", ".go", ".java", ".kt", ".rb", ".php",
    ".c", ".cpp", ".h", ".swift", ".scala", ".dart",
}

# All source extensions we parse (used to skip binary/config files)
ALL_SOURCE_EXTS = _PYTHON_EXTS | _TS_EXTS | _GENERIC_EXTS


def parse_file(rel_path: str, content: str) -> ParseResult:
    """
    Parse a single source file and return its symbols.
    Dispatches to the appropriate language-specific parser.
    Returns an empty list for unsupported file types.
    """
    ext = Path(rel_path).suffix.lower()
    try:
        if ext in _PYTHON_EXTS:
            return parse_python(rel_path, content)
        elif ext in _TS_EXTS:
            return parse_typescript(rel_path, content)
        elif ext in _GENERIC_EXTS:
            return parse_generic(rel_path, content)
    except Exception as e:
        logger.warning(f"Parser error for {rel_path}: {e}")
    return []


def is_parseable(rel_path: str) -> bool:
    """Return True if this file extension is supported by any parser."""
    ext = Path(rel_path).suffix.lower()
    return ext in ALL_SOURCE_EXTS
