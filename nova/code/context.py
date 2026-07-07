"""
nova.code.context
~~~~~~~~~~~~~~~~~
CodeContext — the in-memory semantic model of the project's source code.
All query methods live here so callers never touch the raw indexes directly.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any, Dict, List, Optional

from nova.code.parser.base import CallEdge, Symbol, SymbolKind


@dataclass
class CodeContext:
    """
    Aggregated, searchable semantic index of the project's source code.

    Thread-safe for reads via internal RLock. The engine holds the lock
    during writes (full re-index or incremental update).

    Quick-start::
        ctx = get_code_context()
        hits = ctx.find_symbol("WorkingMemory")
        routes = ctx.find_routes()
    """

    # ── Primary indexes ──────────────────────────────────────────────
    # name → list of symbols (multiple files may define the same name)
    symbol_index: Dict[str, List[Symbol]] = field(default_factory=dict)
    # rel_path → list of symbols defined in that file
    file_symbols: Dict[str, List[Symbol]] = field(default_factory=dict)
    # caller_key → list of outgoing call edges
    call_graph: Dict[str, List[CallEdge]] = field(default_factory=dict)

    # ── Derived / specialised indexes ────────────────────────────────
    route_index:     List[Symbol] = field(default_factory=list)
    component_index: List[Symbol] = field(default_factory=list)
    hook_index:      List[Symbol] = field(default_factory=list)
    model_index:     List[Symbol] = field(default_factory=list)

    # ── Metrics ──────────────────────────────────────────────────────
    last_indexed:     float = field(default_factory=time.time)
    index_duration_s: float = 0.0
    total_symbols:    int   = 0
    total_files:      int   = 0

    # Internal lock — not serialised
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False,
                                   compare=False)

    # ── Public query API ─────────────────────────────────────────────

    def find_symbol(self, name: str, kind: Optional[SymbolKind] = None) -> List[Symbol]:
        """
        Find all symbols matching *name* (exact, case-sensitive).
        Optionally filter by *kind*.
        """
        with self._lock:
            hits = list(self.symbol_index.get(name, []))
        if kind is not None:
            hits = [s for s in hits if s.kind == kind]
        return hits

    def find_references(self, name: str) -> List[Symbol]:
        """
        Return all symbols whose import list or call list mentions *name*.
        Approximates "find usages" without full type resolution.
        """
        results: List[Symbol] = []
        with self._lock:
            for symbols in self.file_symbols.values():
                for sym in symbols:
                    if name in sym.calls:
                        results.append(sym)
        return results

    def find_callers(self, callee_name: str) -> List[CallEdge]:
        """Return all call edges pointing at *callee_name*."""
        results: List[CallEdge] = []
        with self._lock:
            for edges in self.call_graph.values():
                for edge in edges:
                    if edge.callee_name == callee_name:
                        results.append(edge)
        return results

    def find_routes(self, method: Optional[str] = None) -> List[Symbol]:
        """
        Return all HTTP route symbols.
        Optionally filter by HTTP *method* (GET, POST, …).
        """
        with self._lock:
            routes = list(self.route_index)
        if method:
            method = method.upper()
            routes = [r for r in routes
                      if r.metadata.get("http_method", "").upper() == method]
        return routes

    def find_components(self) -> List[Symbol]:
        """Return all React/Vue/Svelte component symbols."""
        with self._lock:
            return list(self.component_index)

    def find_hooks(self) -> List[Symbol]:
        """Return all React hook symbols."""
        with self._lock:
            return list(self.hook_index)

    def find_models(self) -> List[Symbol]:
        """Return all database model symbols."""
        with self._lock:
            return list(self.model_index)

    def symbols_in_file(self, rel_path: str) -> List[Symbol]:
        """Return all symbols defined in the given file."""
        with self._lock:
            return list(self.file_symbols.get(rel_path, []))

    def search(self, query: str, limit: int = 20) -> List[Symbol]:
        """
        Fuzzy name search — returns symbols whose name contains *query*
        (case-insensitive substring match), ranked by name length ascending.
        """
        q = query.lower()
        results: List[Symbol] = []
        with self._lock:
            for name, syms in self.symbol_index.items():
                if q in name.lower():
                    results.extend(syms)
        results.sort(key=lambda s: len(s.name))
        return results[:limit]

    def search_by_pattern(self, pattern: str) -> List[Symbol]:
        """Glob-style pattern search, e.g. 'auth*' or '*.get'."""
        results: List[Symbol] = []
        with self._lock:
            for name, syms in self.symbol_index.items():
                if fnmatch(name.lower(), pattern.lower()):
                    results.extend(syms)
        return results

    def all_symbols(self) -> List[Symbol]:
        """Flat list of every indexed symbol (use with care on large projects)."""
        with self._lock:
            return [s for syms in self.file_symbols.values() for s in syms]

    def stats(self) -> Dict[str, Any]:
        """Return a summary dict for dashboard/TTS."""
        with self._lock:
            return {
                "total_symbols": self.total_symbols,
                "total_files": self.total_files,
                "routes": len(self.route_index),
                "components": len(self.component_index),
                "models": len(self.model_index),
                "hooks": len(self.hook_index),
                "last_indexed": self.last_indexed,
                "index_duration_s": self.index_duration_s,
            }

    # ── Mutation helpers (called by engine, not by consumers) ────────

    def _add_symbols(self, rel_path: str, symbols: List[Symbol]) -> None:
        """Insert symbols for a file. Does NOT remove old ones first."""
        with self._lock:
            self.file_symbols.setdefault(rel_path, []).extend(symbols)
            for sym in symbols:
                self.symbol_index.setdefault(sym.name, []).append(sym)
            self._rebuild_derived()

    def _remove_file(self, rel_path: str) -> None:
        """Remove all symbols belonging to *rel_path*."""
        with self._lock:
            old = self.file_symbols.pop(rel_path, [])
            for sym in old:
                bucket = self.symbol_index.get(sym.name, [])
                self.symbol_index[sym.name] = [s for s in bucket if s.file != rel_path]
                if not self.symbol_index[sym.name]:
                    del self.symbol_index[sym.name]
            # Remove call edges originating from this file
            stale_keys = [k for k in self.call_graph if k.startswith(rel_path + ":")]
            for k in stale_keys:
                del self.call_graph[k]
            self._rebuild_derived()

    def _replace_file(self, rel_path: str, symbols: List[Symbol],
                      edges: List[CallEdge]) -> None:
        """Atomically replace all data for a single file."""
        with self._lock:
            self._remove_file(rel_path)
            self.file_symbols[rel_path] = symbols
            for sym in symbols:
                self.symbol_index.setdefault(sym.name, []).append(sym)
            if edges:
                # Key by first edge's caller_key prefix (file-level)
                key = f"{rel_path}"
                # Store per-caller-symbol
                for edge in edges:
                    self.call_graph.setdefault(edge.caller_key, []).append(edge)
            self._rebuild_derived()

    def _rebuild_derived(self) -> None:
        """Recompute the specialised indexes from file_symbols."""
        routes:     List[Symbol] = []
        components: List[Symbol] = []
        hooks:      List[Symbol] = []
        models:     List[Symbol] = []
        total = 0

        for syms in self.file_symbols.values():
            for sym in syms:
                total += 1
                if sym.kind == SymbolKind.ROUTE:
                    routes.append(sym)
                elif sym.kind == SymbolKind.COMPONENT:
                    components.append(sym)
                elif sym.kind == SymbolKind.HOOK:
                    hooks.append(sym)
                elif sym.kind == SymbolKind.MODEL:
                    models.append(sym)

        self.route_index     = routes
        self.component_index = components
        self.hook_index      = hooks
        self.model_index     = models
        self.total_symbols   = total
        self.total_files     = len(self.file_symbols)
