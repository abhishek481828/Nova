"""
nova.code.parser.base
~~~~~~~~~~~~~~~~~~~~~
Shared enumerations and data classes used by every language parser.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class SymbolKind(str, Enum):
    """Semantic category of a code symbol."""
    CLASS        = "class"
    FUNCTION     = "function"
    METHOD       = "method"
    ASYNC_FUNCTION = "async_function"
    ASYNC_METHOD = "async_method"
    INTERFACE    = "interface"
    ENUM         = "enum"
    VARIABLE     = "variable"
    CONSTANT     = "constant"
    IMPORT       = "import"
    EXPORT       = "export"
    # Framework-specific
    ROUTE        = "route"        # HTTP endpoint
    MODEL        = "model"        # DB model / schema
    COMPONENT    = "component"    # React/Vue/Svelte component
    HOOK         = "hook"         # React hook (use*)
    MIDDLEWARE   = "middleware"
    CONTROLLER   = "controller"
    SERVICE      = "service"
    TYPE_ALIAS   = "type_alias"   # TypeScript type / interface
    DECORATOR    = "decorator"
    UNKNOWN      = "unknown"


@dataclass
class Symbol:
    """
    A single named code entity extracted from a source file.

    All parsers produce a list of Symbol objects. The CodeIntelligenceEngine
    then aggregates them into searchable indexes.
    """
    name: str
    kind: SymbolKind
    file: str            # relative path from project root
    line: int            # 1-indexed start line
    end_line: int        # 1-indexed end line (best effort)
    signature: str = "" # e.g. "def foo(a, b) -> int"
    docstring: str = ""
    parent: Optional[str] = None   # enclosing class/function name
    decorators: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # raw callee names this symbol calls (populated by parsers)
    calls: List[str] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        """Return 'ClassName.method_name' or just 'name'."""
        if self.parent:
            return f"{self.parent}.{self.name}"
        return self.name

    @property
    def location(self) -> str:
        """Compact location string for display."""
        return f"{self.file}:{self.line}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "signature": self.signature,
            "docstring": self.docstring,
            "parent": self.parent,
            "decorators": self.decorators,
            "metadata": self.metadata,
        }


@dataclass
class CallEdge:
    """
    A directed edge from a caller symbol to a callee name.
    Callee is stored as a raw name string (resolved later by the engine).
    """
    caller_file: str    # relative path
    caller_name: str    # qualified name of the calling symbol
    caller_line: int
    callee_name: str    # name being called (may be unresolved)

    @property
    def caller_key(self) -> str:
        return f"{self.caller_file}:{self.caller_name}"


# Typing alias used by parsers
ParseResult = List[Symbol]
