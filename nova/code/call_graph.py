"""
nova.code.call_graph
~~~~~~~~~~~~~~~~~~~~
Second-pass call graph builder.

After all symbols are extracted from a file, the builder:
  1. Looks at each symbol's `calls` list (raw callee names from parsers).
  2. Emits a CallEdge for every name that also appears in the global
     symbol_index (i.e., a name that is actually defined somewhere in
     the project).
  3. Also emits edges for callee names that don't resolve — these are
     stored as "unresolved" edges and are useful for "who calls X?" queries.

This approach is name-based (not type-aware), which is fast, dependency-free,
and sufficient for v1 answering "who calls this function?".
"""
from __future__ import annotations

import logging
from typing import Dict, List

from nova.code.parser.base import CallEdge, Symbol

logger = logging.getLogger("nova.code.call_graph")


class CallGraphBuilder:
    """
    Builds CallEdge objects from a list of symbols and the current
    global symbol_index.
    """

    def build_edges_for_file(
        self,
        rel_path: str,
        symbols: List[Symbol],
        known_names: set,
    ) -> List[CallEdge]:
        """
        For each symbol in the file, emit a CallEdge for every name in
        its `calls` list that appears in `known_names`.

        *known_names* — the set of all symbol names currently indexed.
        It is acceptable to pass all names (including unresolved ones) to
        capture cross-file references.
        """
        edges: List[CallEdge] = []
        for sym in symbols:
            for callee in sym.calls:
                if not callee or callee == sym.name:
                    continue  # skip self-calls and empty
                edges.append(CallEdge(
                    caller_file=rel_path,
                    caller_name=sym.qualified_name,
                    caller_line=sym.line,
                    callee_name=callee,
                ))
        return edges

    def build_edges_for_project(
        self,
        file_symbols: Dict[str, List[Symbol]],
    ) -> Dict[str, List[CallEdge]]:
        """
        Build call graph for the entire project.
        Returns a dict: caller_key → list of CallEdge.
        """
        all_names: set = set()
        for syms in file_symbols.values():
            for s in syms:
                all_names.add(s.name)

        graph: Dict[str, List[CallEdge]] = {}
        for rel_path, syms in file_symbols.items():
            edges = self.build_edges_for_file(rel_path, syms, all_names)
            for edge in edges:
                graph.setdefault(edge.caller_key, []).append(edge)

        total = sum(len(v) for v in graph.values())
        logger.debug(f"Call graph: {total} edges across {len(graph)} callers")
        return graph


# Module-level singleton
_builder = CallGraphBuilder()


def build_call_graph(
    file_symbols: Dict[str, List[Symbol]],
) -> Dict[str, List[CallEdge]]:
    return _builder.build_edges_for_project(file_symbols)


def build_edges_for_file(
    rel_path: str,
    symbols: List[Symbol],
    known_names: set,
) -> List[CallEdge]:
    return _builder.build_edges_for_file(rel_path, symbols, known_names)
