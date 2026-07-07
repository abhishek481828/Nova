"""
nova.code
~~~~~~~~~
Code Intelligence Engine — public API.

Quick-start::
    from nova.code import get_code_context, CodeIntelligenceEngine

    ctx = get_code_context()
    if ctx:
        for sym in ctx.find_symbol("WorkingMemory"):
            print(sym.location, sym.kind)
        for route in ctx.find_routes():
            print(route.metadata.get("path"), route.metadata.get("http_method"))
"""
from nova.code.engine import CodeIntelligenceEngine
from nova.code.context import CodeContext
from nova.code.parser.base import Symbol, SymbolKind, CallEdge


def get_code_context() -> "CodeContext | None":
    """
    Return the current CodeContext from the singleton engine, or None if
    the initial indexing has not yet completed.

    This is the primary entry point for all Nova components that need
    code intelligence without managing the engine lifecycle themselves.
    """
    return CodeIntelligenceEngine().get_context()


__all__ = [
    "CodeIntelligenceEngine",
    "CodeContext",
    "Symbol",
    "SymbolKind",
    "CallEdge",
    "get_code_context",
]
