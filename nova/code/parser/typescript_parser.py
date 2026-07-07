"""
nova.code.parser.typescript_parser
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Regex-based parser for TypeScript / JavaScript files.
(.ts, .tsx, .js, .jsx, .mjs)

Extracts:
  - class declarations
  - function declarations (regular, arrow, async)
  - interface and type aliases (TS)
  - enum declarations
  - export statements (named + default)
  - React functional components (PascalCase arrow functions / functions)
  - React hooks (use* convention)
  - Express route registrations (app.get / router.post / etc.)
  - Next.js API route handlers (export default function handler)
  - module-level const/let/var declarations
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional

from nova.code.parser.base import ParseResult, Symbol, SymbolKind

logger = logging.getLogger("nova.code.parser.typescript")

# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────────────────────────────────────

# class Foo [extends Bar] [implements Baz]
_CLASS_RE = re.compile(
    r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"
    r"(?:\s+extends\s+(\w+))?(?:\s+implements\s+[\w,\s]+)?",
    re.MULTILINE,
)

# interface Foo [extends Bar]
_INTERFACE_RE = re.compile(
    r"^(?:export\s+)?interface\s+(\w+)", re.MULTILINE
)

# type Foo = ...
_TYPE_ALIAS_RE = re.compile(
    r"^(?:export\s+)?type\s+(\w+)\s*(?:<[^>]*>)?\s*=", re.MULTILINE
)

# enum Foo { ... }
_ENUM_RE = re.compile(
    r"^(?:export\s+)?(?:const\s+)?enum\s+(\w+)", re.MULTILINE
)

# function foo(...) { or async function foo(...) {
_FUNC_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:(async)\s+)?function\s+(\w+)\s*\(",
    re.MULTILINE,
)

# const foo = (...) => or const foo = async (...) =>
_ARROW_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:(async)\s*)?"
    r"(?:\([^)]*\)|[A-Za-z_]\w*)\s*(?::\s*[^=]+)?\s*=>",
    re.MULTILINE,
)

# const foo = function(...) {
_FUNC_EXPR_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:(async)\s+)?function\s*\(",
    re.MULTILINE,
)

# export default function handler / export default class Foo
_EXPORT_DEFAULT_RE = re.compile(
    r"^export\s+default\s+(?:(async)\s+)?function\s+(\w+)\s*\(",
    re.MULTILINE,
)

# Express / Fastify routes: app.get('/path', ...) or router.post('/path', ...)
_EXPRESS_ROUTE_RE = re.compile(
    r"^(?:\w+)\.(get|post|put|delete|patch|options|all)\s*\(\s*['\"`]([^'\"` ]+)['\"`]",
    re.MULTILINE | re.IGNORECASE,
)

# const Foo: React.FC = or function Foo( returning JSX
_REACT_COMPONENT_RE = re.compile(
    r"(?:const|function)\s+([A-Z][A-Za-z0-9_]*)\s*"
    r"(?::\s*(?:React\.)?(?:FC|FunctionComponent|VFC|ComponentType)[^=]*)?",
    re.MULTILINE,
)

# React hooks: const useAuth = ... or function useAuth(
_HOOK_RE = re.compile(
    r"(?:const|function)\s+(use[A-Z][A-Za-z0-9_]*)\s*[=(]",
    re.MULTILINE,
)

# Simple call extraction: foo( or bar.baz(
_CALL_RE = re.compile(r"\b(\w+)\s*\(", re.MULTILINE)

# const/let/var FOO = ...
_CONST_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+([A-Z][A-Z0-9_]{2,})\s*=",
    re.MULTILINE,
)

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head", "all"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _line_of(content: str, pos: int) -> int:
    """1-indexed line number for a byte position in the string."""
    return content[:pos].count("\n") + 1


def _collect_calls(content: str) -> List[str]:
    names = _CALL_RE.findall(content)
    keywords = {
        "if", "for", "while", "switch", "catch", "return", "typeof", "instanceof",
        "new", "delete", "void", "throw", "async", "await", "import", "export",
    }
    return list(dict.fromkeys(n for n in names if n not in keywords))[:60]


def _is_react_component(name: str) -> bool:
    """Heuristic: PascalCase → React component."""
    return bool(name) and name[0].isupper() and not name.isupper()


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

class TypeScriptParser:
    def parse_file(self, rel_path: str, content: str) -> ParseResult:
        symbols: List[Symbol] = []
        seen: set = set()
        all_calls = _collect_calls(content)

        def _add(sym: Symbol) -> None:
            key = (sym.name, sym.kind, sym.line)
            if key not in seen:
                seen.add(key)
                sym.calls.extend(all_calls)
                symbols.append(sym)

        # ── Classes ──────────────────────────────────────────────────
        for m in _CLASS_RE.finditer(content):
            name = m.group(1)
            line = _line_of(content, m.start())
            _add(Symbol(name=name, kind=SymbolKind.CLASS, file=rel_path,
                        line=line, end_line=line,
                        signature=f"class {name}",
                        metadata={"base": m.group(2) or ""}))

        # ── Interfaces ───────────────────────────────────────────────
        for m in _INTERFACE_RE.finditer(content):
            name = m.group(1)
            line = _line_of(content, m.start())
            _add(Symbol(name=name, kind=SymbolKind.INTERFACE, file=rel_path,
                        line=line, end_line=line,
                        signature=f"interface {name}"))

        # ── Type aliases ─────────────────────────────────────────────
        for m in _TYPE_ALIAS_RE.finditer(content):
            name = m.group(1)
            line = _line_of(content, m.start())
            _add(Symbol(name=name, kind=SymbolKind.TYPE_ALIAS, file=rel_path,
                        line=line, end_line=line,
                        signature=f"type {name}"))

        # ── Enums ────────────────────────────────────────────────────
        for m in _ENUM_RE.finditer(content):
            name = m.group(1)
            line = _line_of(content, m.start())
            _add(Symbol(name=name, kind=SymbolKind.ENUM, file=rel_path,
                        line=line, end_line=line,
                        signature=f"enum {name}"))

        # ── Named functions ──────────────────────────────────────────
        for m in _FUNC_RE.finditer(content):
            is_async = bool(m.group(1))
            name = m.group(2)
            line = _line_of(content, m.start())
            kind = _classify_js_func(name, is_async)
            _add(Symbol(name=name, kind=kind, file=rel_path,
                        line=line, end_line=line,
                        signature=f"{'async ' if is_async else ''}function {name}()"))

        # ── Export default function ───────────────────────────────────
        for m in _EXPORT_DEFAULT_RE.finditer(content):
            is_async = bool(m.group(1))
            name = m.group(2)
            line = _line_of(content, m.start())
            kind = SymbolKind.ROUTE if name.lower() == "handler" else _classify_js_func(name, is_async)
            meta = {"http_method": "GET"} if kind == SymbolKind.ROUTE else {}
            _add(Symbol(name=name, kind=kind, file=rel_path,
                        line=line, end_line=line,
                        signature=f"export default {'async ' if is_async else ''}function {name}()",
                        metadata=meta))

        # ── Arrow functions ──────────────────────────────────────────
        for m in _ARROW_RE.finditer(content):
            name = m.group(1)
            is_async = bool(m.group(2))
            line = _line_of(content, m.start())
            kind = _classify_js_func(name, is_async)
            _add(Symbol(name=name, kind=kind, file=rel_path,
                        line=line, end_line=line,
                        signature=f"{'async ' if is_async else ''}const {name} = () =>"))

        # ── Function expressions ─────────────────────────────────────
        for m in _FUNC_EXPR_RE.finditer(content):
            name = m.group(1)
            is_async = bool(m.group(2))
            line = _line_of(content, m.start())
            kind = _classify_js_func(name, is_async)
            _add(Symbol(name=name, kind=kind, file=rel_path,
                        line=line, end_line=line,
                        signature=f"const {name} = {'async ' if is_async else ''}function()"))

        # ── Express routes ───────────────────────────────────────────
        for m in _EXPRESS_ROUTE_RE.finditer(content):
            http_method = m.group(1).upper()
            path = m.group(2)
            line = _line_of(content, m.start())
            route_name = f"{http_method}:{path}"
            _add(Symbol(name=route_name, kind=SymbolKind.ROUTE, file=rel_path,
                        line=line, end_line=line,
                        signature=f"router.{http_method.lower()}('{path}')",
                        metadata={"http_method": http_method, "path": path}))

        # ── Constants (ALL_CAPS) ─────────────────────────────────────
        for m in _CONST_RE.finditer(content):
            name = m.group(1)
            line = _line_of(content, m.start())
            _add(Symbol(name=name, kind=SymbolKind.CONSTANT, file=rel_path,
                        line=line, end_line=line,
                        signature=f"const {name}"))

        return symbols


def _classify_js_func(name: str, is_async: bool) -> SymbolKind:
    if name == "handler":
        return SymbolKind.ROUTE  # Next.js API route handler
    if name.startswith("use") and len(name) > 3 and name[3].isupper():
        return SymbolKind.HOOK
    if _is_react_component(name):
        return SymbolKind.COMPONENT
    return SymbolKind.ASYNC_FUNCTION if is_async else SymbolKind.FUNCTION


_parser = TypeScriptParser()


def parse_typescript(rel_path: str, content: str) -> ParseResult:
    return _parser.parse_file(rel_path, content)
