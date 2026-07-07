"""
nova.code.parser.generic_parser
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Regex-based fallback parser for Rust, Go, Java, Ruby, PHP, C, C++, Swift, Kotlin.
Extracts class names and function/method signatures at a surface level.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List

from nova.code.parser.base import ParseResult, Symbol, SymbolKind

logger = logging.getLogger("nova.code.parser.generic")


def _line_of(content: str, pos: int) -> int:
    return content[:pos].count("\n") + 1


# ─────────────────────────────────────────────────────────────────────────────
# Per-extension patterns
# ─────────────────────────────────────────────────────────────────────────────

_PATTERNS: Dict[str, List] = {
    # Rust
    ".rs": [
        (SymbolKind.CLASS,     re.compile(r"^pub\s+struct\s+(\w+)", re.MULTILINE)),
        (SymbolKind.CLASS,     re.compile(r"^struct\s+(\w+)", re.MULTILINE)),
        (SymbolKind.INTERFACE, re.compile(r"^(?:pub\s+)?trait\s+(\w+)", re.MULTILINE)),
        (SymbolKind.ENUM,      re.compile(r"^(?:pub\s+)?enum\s+(\w+)", re.MULTILINE)),
        (SymbolKind.FUNCTION,  re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*\(", re.MULTILINE)),
    ],
    # Go
    ".go": [
        (SymbolKind.CLASS,     re.compile(r"^type\s+(\w+)\s+struct", re.MULTILINE)),
        (SymbolKind.INTERFACE, re.compile(r"^type\s+(\w+)\s+interface", re.MULTILINE)),
        (SymbolKind.FUNCTION,  re.compile(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(", re.MULTILINE)),
    ],
    # Java
    ".java": [
        (SymbolKind.CLASS,     re.compile(r"^(?:public\s+)?(?:abstract\s+)?class\s+(\w+)", re.MULTILINE)),
        (SymbolKind.INTERFACE, re.compile(r"^(?:public\s+)?interface\s+(\w+)", re.MULTILINE)),
        (SymbolKind.ENUM,      re.compile(r"^(?:public\s+)?enum\s+(\w+)", re.MULTILINE)),
        (SymbolKind.METHOD,    re.compile(
            r"^\s+(?:public|private|protected|static|final|\s)+"
            r"[\w<>\[\]]+\s+(\w+)\s*\(", re.MULTILINE)),
    ],
    # Kotlin
    ".kt": [
        (SymbolKind.CLASS,     re.compile(r"^(?:data\s+)?(?:open\s+)?class\s+(\w+)", re.MULTILINE)),
        (SymbolKind.INTERFACE, re.compile(r"^interface\s+(\w+)", re.MULTILINE)),
        (SymbolKind.FUNCTION,  re.compile(r"^(?:suspend\s+)?fun\s+(\w+)\s*\(", re.MULTILINE)),
    ],
    # Ruby
    ".rb": [
        (SymbolKind.CLASS,    re.compile(r"^class\s+(\w+)", re.MULTILINE)),
        (SymbolKind.CLASS,    re.compile(r"^module\s+(\w+)", re.MULTILINE)),
        (SymbolKind.METHOD,   re.compile(r"^\s+def\s+(\w+)", re.MULTILINE)),
        (SymbolKind.FUNCTION, re.compile(r"^def\s+(\w+)", re.MULTILINE)),
    ],
    # PHP
    ".php": [
        (SymbolKind.CLASS,    re.compile(r"^(?:abstract\s+)?class\s+(\w+)", re.MULTILINE)),
        (SymbolKind.INTERFACE,re.compile(r"^interface\s+(\w+)", re.MULTILINE)),
        (SymbolKind.FUNCTION, re.compile(r"^(?:public|protected|private|static|\s)*function\s+(\w+)\s*\(", re.MULTILINE)),
    ],
    # C / C++
    ".c": [
        (SymbolKind.FUNCTION, re.compile(r"^[\w\*]+\s+(\w+)\s*\([^;]+\)\s*\{", re.MULTILINE)),
    ],
    ".cpp": [
        (SymbolKind.CLASS,    re.compile(r"^(?:class|struct)\s+(\w+)", re.MULTILINE)),
        (SymbolKind.FUNCTION, re.compile(r"^\w+\s+\w+::(\w+)\s*\(", re.MULTILINE)),
    ],
    ".h": [
        (SymbolKind.CLASS,    re.compile(r"^(?:class|struct)\s+(\w+)", re.MULTILINE)),
    ],
    # Swift
    ".swift": [
        (SymbolKind.CLASS,    re.compile(r"^(?:final\s+)?class\s+(\w+)", re.MULTILINE)),
        (SymbolKind.INTERFACE,re.compile(r"^protocol\s+(\w+)", re.MULTILINE)),
        (SymbolKind.ENUM,     re.compile(r"^enum\s+(\w+)", re.MULTILINE)),
        (SymbolKind.FUNCTION, re.compile(r"^\s*func\s+(\w+)\s*\(", re.MULTILINE)),
    ],
    # Scala
    ".scala": [
        (SymbolKind.CLASS,    re.compile(r"^(?:case\s+)?class\s+(\w+)", re.MULTILINE)),
        (SymbolKind.INTERFACE,re.compile(r"^trait\s+(\w+)", re.MULTILINE)),
        (SymbolKind.FUNCTION, re.compile(r"^\s+def\s+(\w+)\s*[(\[]", re.MULTILINE)),
    ],
    # Dart
    ".dart": [
        (SymbolKind.CLASS,    re.compile(r"^class\s+(\w+)", re.MULTILINE)),
        (SymbolKind.FUNCTION, re.compile(r"^\s+\w+\s+(\w+)\s*\(", re.MULTILINE)),
    ],
}


class GenericParser:
    def parse_file(self, rel_path: str, content: str) -> ParseResult:
        ext = "." + rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
        patterns = _PATTERNS.get(ext, [])
        if not patterns:
            return []

        symbols: List[Symbol] = []
        seen: set = set()

        for kind, pattern in patterns:
            for m in pattern.finditer(content):
                name = m.group(1)
                line = _line_of(content, m.start())
                key = (name, kind, line)
                if key in seen:
                    continue
                seen.add(key)
                symbols.append(Symbol(
                    name=name,
                    kind=kind,
                    file=rel_path,
                    line=line,
                    end_line=line,
                    signature=f"{kind.value} {name}",
                ))
        return symbols


_parser = GenericParser()


def parse_generic(rel_path: str, content: str) -> ParseResult:
    return _parser.parse_file(rel_path, content)
