"""
nova.code.parser.python_parser
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Full AST-based parser for Python (.py) files.

Extracts:
  - Classes (+ base classes)
  - Functions and async functions
  - Methods and async methods (inside classes)
  - Module-level constants / variable assignments
  - Decorators (and parses Flask/FastAPI/Django route decorators)
  - Call nodes for call-graph edges
  - Docstrings
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import List, Optional

from nova.code.parser.base import CallEdge, ParseResult, Symbol, SymbolKind

logger = logging.getLogger("nova.code.parser.python")

# ─────────────────────────────────────────────────────────────────────────────
# Route decorator patterns
# ─────────────────────────────────────────────────────────────────────────────
_ROUTE_DECORATORS = {
    # Flask
    "route", "get", "post", "put", "delete", "patch",
    "app.route", "bp.route", "blueprint.route",
    # FastAPI
    "router.get", "router.post", "router.put", "router.delete",
    "router.patch", "router.options", "router.head",
    "app.get", "app.post", "app.put", "app.delete", "app.patch",
    # Django (class-based views are classes, handled by class detection)
}
_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}

# Model base classes (Django, SQLAlchemy, Pydantic, etc.)
_MODEL_BASES = {
    "Model", "Base", "BaseModel", "SQLModel", "Document",
    "DeclarativeBase", "MongoModel", "Schema",
}


def _decorator_name(node: ast.expr) -> str:
    """Flatten a decorator AST node to its dotted name, e.g. 'app.route'."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_decorator_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _extract_route_meta(decorator: ast.expr) -> dict:
    """Pull HTTP path and method from a route decorator node."""
    meta: dict = {}
    if not isinstance(decorator, ast.Call):
        return meta
    # First positional arg is the path
    if decorator.args:
        arg = decorator.args[0]
        if isinstance(arg, ast.Constant):
            meta["path"] = arg.value
    # Keyword args: methods=[...]
    for kw in decorator.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
            methods = [
                elt.value.upper()
                for elt in kw.value.elts
                if isinstance(elt, ast.Constant)
            ]
            meta["http_methods"] = methods
            if methods:
                meta["http_method"] = methods[0]
    # Infer method from decorator name (e.g. @app.get → GET)
    dname = _decorator_name(decorator.func if isinstance(decorator, ast.Call)
                             else decorator)
    suffix = dname.split(".")[-1].lower()
    if suffix in _HTTP_METHODS and "http_method" not in meta:
        meta["http_method"] = suffix.upper()
    return meta


def _get_docstring(node: ast.AST) -> str:
    """Extract docstring from a function/class body."""
    try:
        return ast.get_docstring(node) or ""  # type: ignore[arg-type]
    except Exception:
        return ""


def _collect_calls(node: ast.AST) -> List[str]:
    """Walk an AST node and collect all direct function/attribute call names."""
    calls: List[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                calls.append(func.id)
            elif isinstance(func, ast.Attribute):
                calls.append(func.attr)
    return list(dict.fromkeys(calls))  # deduplicate, preserve order


def _is_model_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = ""
        if isinstance(base, ast.Name):
            name = base.id
        elif isinstance(base, ast.Attribute):
            name = base.attr
        if name in _MODEL_BASES:
            return True
    return False


def _sig_from_args(args: ast.arguments) -> str:
    """Build a readable argument signature string."""
    parts: List[str] = []
    # positional
    for arg in args.args:
        parts.append(arg.arg)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    for arg in args.kwonlyargs:
        parts.append(arg.arg)
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return f"({', '.join(parts)})"


# ─────────────────────────────────────────────────────────────────────────────
# Main parser
# ─────────────────────────────────────────────────────────────────────────────

class PythonParser:
    """Parse a single Python source file into a list of Symbol objects."""

    def parse_file(self, rel_path: str, content: str) -> ParseResult:
        try:
            tree = ast.parse(content, filename=rel_path)
        except SyntaxError as e:
            logger.debug(f"Syntax error in {rel_path}: {e}")
            return []

        symbols: List[Symbol] = []
        self._visit_module(tree, rel_path, symbols)
        return symbols

    def _visit_module(self, tree: ast.Module, rel_path: str,
                      symbols: List[Symbol]) -> None:
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                self._visit_class(node, rel_path, symbols, parent=None)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._visit_function(node, rel_path, symbols, parent=None)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                self._visit_assignment(node, rel_path, symbols)

    def _visit_class(self, node: ast.ClassDef, rel_path: str,
                     symbols: List[Symbol], parent: Optional[str]) -> None:
        decs = [_decorator_name(d) for d in node.decorator_list]
        kind = SymbolKind.MODEL if _is_model_class(node) else SymbolKind.CLASS
        bases = [
            (n.id if isinstance(n, ast.Name) else
             n.attr if isinstance(n, ast.Attribute) else "")
            for n in node.bases
        ]
        sym = Symbol(
            name=node.name,
            kind=kind,
            file=rel_path,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=f"class {node.name}({', '.join(b for b in bases if b)})",
            docstring=_get_docstring(node),
            parent=parent,
            decorators=decs,
            metadata={"bases": bases},
            calls=_collect_calls(node),
        )
        symbols.append(sym)

        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._visit_function(child, rel_path, symbols, parent=node.name)
            elif isinstance(child, ast.ClassDef):
                self._visit_class(child, rel_path, symbols, parent=node.name)

    def _visit_function(self, node, rel_path: str,
                        symbols: List[Symbol], parent: Optional[str]) -> None:
        is_async = isinstance(node, ast.AsyncFunctionDef)
        decs = [_decorator_name(d) for d in node.decorator_list]
        decs_raw = node.decorator_list

        # Determine kind
        kind: SymbolKind
        route_meta: dict = {}
        is_route = False

        for dec, dec_node in zip(decs, decs_raw):
            dec_base = dec.split(".")[-1].lower()
            if dec in _ROUTE_DECORATORS or dec_base in _ROUTE_DECORATORS:
                is_route = True
                route_meta = _extract_route_meta(dec_node)
                break

        if is_route:
            kind = SymbolKind.ROUTE
        elif parent:
            kind = SymbolKind.ASYNC_METHOD if is_async else SymbolKind.METHOD
        else:
            kind = SymbolKind.ASYNC_FUNCTION if is_async else SymbolKind.FUNCTION

        sig_args = _sig_from_args(node.args)
        prefix = "async def" if is_async else "def"
        sig = f"{prefix} {node.name}{sig_args}"

        sym = Symbol(
            name=node.name,
            kind=kind,
            file=rel_path,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=sig,
            docstring=_get_docstring(node),
            parent=parent,
            decorators=decs,
            metadata=route_meta,
            calls=_collect_calls(node),
        )
        symbols.append(sym)

    def _visit_assignment(self, node, rel_path: str,
                          symbols: List[Symbol]) -> None:
        """Capture module-level constants (ALL_CAPS) and annotated variables."""
        targets: List[str] = []
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    targets.append(t.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                targets.append(node.target.id)

        for name in targets:
            if name.isupper() and len(name) > 1:
                kind = SymbolKind.CONSTANT
            else:
                kind = SymbolKind.VARIABLE
            symbols.append(Symbol(
                name=name,
                kind=kind,
                file=rel_path,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                signature=name,
            ))


# Module-level singleton
_parser = PythonParser()


def parse_python(rel_path: str, content: str) -> ParseResult:
    """Parse a Python source file. Returns a list of Symbol objects."""
    return _parser.parse_file(rel_path, content)
