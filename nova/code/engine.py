"""
nova.code.engine
~~~~~~~~~~~~~~~~
CodeIntelligenceEngine — thread-safe singleton that orchestrates
parsing, indexing, call-graph building, and incremental updates.

Integration with Project Awareness Engine:
  - Reads file paths from ProjectContext.file_index (no double filesystem scan).
  - Registers itself as a change listener on ProjectAwarenessEngine so that
    file-change events trigger single-file re-parses (not full re-index).
  - Runs the initial parse in a ThreadPoolExecutor to parallelise work.

Lifecycle::
    from nova.code.engine import CodeIntelligenceEngine
    engine = CodeIntelligenceEngine()
    engine.start_in_background()          # non-blocking
    ctx = engine.get_context()            # returns None until ready
    engine.stop()                         # on shutdown
"""
from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from pathlib import Path
from typing import List, Optional

from nova.code.call_graph import build_call_graph, build_edges_for_file
from nova.code.context import CodeContext
from nova.code.parser import ALL_SOURCE_EXTS, is_parseable, parse_file
from nova.code.parser.base import Symbol

logger = logging.getLogger("nova.code.engine")

# Max worker threads for initial parallel parse
_MAX_WORKERS = 4


class CodeIntelligenceEngine:
    """
    Thread-safe singleton that turns a ProjectContext into a CodeContext.

    Design decisions:
    - Reads file list from ProjectContext.file_index — no extra FS walk.
    - Registers as a secondary on_change listener on ProjectAwarenessEngine.
    - Full parse runs in parallel (ThreadPoolExecutor).
    - Incremental updates touch only the changed file.
    """

    _instance: Optional["CodeIntelligenceEngine"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "CodeIntelligenceEngine":
        with cls._instance_lock:
            if cls._instance is None:
                obj = super().__new__(cls)
                obj._initialised = False
                cls._instance = obj
            return cls._instance

    def __init__(self) -> None:
        if self._initialised:
            return
        self._context: Optional[CodeContext] = None
        self._context_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._initialised = True

    # ── Public API ──────────────────────────────────────────────────

    def get_context(self) -> Optional[CodeContext]:
        """Return the current CodeContext, or None if not yet indexed."""
        with self._context_lock:
            return self._context

    def start_in_background(self) -> None:
        """
        Wait for the ProjectAwarenessEngine to have a context, then parse.
        Safe to call at daemon startup before the project scan completes.
        """
        t = threading.Thread(
            target=self._wait_and_index,
            name="CodeIntelligence-Startup",
            daemon=True,
        )
        t.start()
        logger.info("CodeIntelligenceEngine: background indexing scheduled.")

    def stop(self) -> None:
        self._stop_event.set()
        logger.info("CodeIntelligenceEngine stopped.")

    # ── Incremental update (called by PAE change listener) ─────────

    def on_file_change(self, event_type: str, rel_path: str,
                       project_root: Path) -> None:
        """
        Called by the ProjectAwarenessEngine on every file-system event.
        Only re-parses the single changed file.
        """
        with self._context_lock:
            ctx = self._context
        if ctx is None:
            return

        if not is_parseable(rel_path):
            return

        if event_type == "deleted":
            ctx._remove_file(rel_path)
            logger.debug(f"[CIE] Removed symbols for: {rel_path}")
            return

        full_path = project_root / rel_path
        if not full_path.exists():
            return

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
            symbols = parse_file(rel_path, content)
            # Build edges for this file relative to current known names
            with self._context_lock:
                ctx = self._context
            if ctx is None:
                return
            with ctx._lock:
                known_names = set(ctx.symbol_index.keys())
            edges = build_edges_for_file(rel_path, symbols, known_names)
            ctx._replace_file(rel_path, symbols, edges)
            logger.debug(
                f"[CIE] Re-indexed {rel_path}: "
                f"{len(symbols)} symbols, {len(edges)} edges"
            )
        except Exception as e:
            logger.warning(f"[CIE] Failed to update {rel_path}: {e}")

    # ── Internal ────────────────────────────────────────────────────

    def _wait_and_index(self) -> None:
        """Wait for ProjectAwarenessEngine context, then run full index."""
        try:
            from nova.project.engine import ProjectAwarenessEngine
        except ImportError:
            logger.warning("[CIE] ProjectAwarenessEngine not available.")
            return

        pae = ProjectAwarenessEngine()

        # Register change listener (safe if already registered)
        pae.register_change_listener(self._change_listener_factory(pae))

        # Wait up to 120s for the project context to be ready
        for _ in range(120):
            if self._stop_event.is_set():
                return
            project_ctx = pae.get_context()
            if project_ctx is not None:
                break
            time.sleep(1)
        else:
            logger.warning("[CIE] Timed out waiting for ProjectContext.")
            return

        self._full_index(project_ctx)

    def _change_listener_factory(self, pae):
        """Return a bound closure for the PAE change callback."""
        def _listener(event_type: str, path_str: str) -> None:
            try:
                ctx = pae.get_context()
                if ctx:
                    self.on_file_change(event_type, path_str, ctx.root)
            except Exception as e:
                logger.debug(f"[CIE] Change listener error: {e}")
        return _listener

    def _full_index(self, project_ctx) -> None:
        """Parse all source files in the project in parallel."""
        t0 = time.perf_counter()
        root = project_ctx.root
        file_index = project_ctx.file_index

        source_files = [
            rel for rel in file_index
            if is_parseable(rel)
        ]

        logger.info(f"[CIE] Parsing {len(source_files)} source files under {root}…")

        file_symbols = {}
        parse_errors = 0

        def _parse_one(rel_path: str):
            full = root / rel_path
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
                return rel_path, parse_file(rel_path, content)
            except Exception as e:
                logger.debug(f"[CIE] Parse error {rel_path}: {e}")
                return rel_path, []

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=_MAX_WORKERS, thread_name_prefix="CIE-Parse"
        ) as executor:
            futures = {executor.submit(_parse_one, r): r for r in source_files}
            for future in concurrent.futures.as_completed(futures):
                rel_path, syms = future.result()
                if syms:
                    file_symbols[rel_path] = syms
                else:
                    parse_errors += 1

        # Build call graph
        call_graph = build_call_graph(file_symbols)

        # Assemble CodeContext
        elapsed = time.perf_counter() - t0
        code_ctx = CodeContext(
            last_indexed=time.time(),
            index_duration_s=round(elapsed, 3),
        )

        with code_ctx._lock:
            for rel_path, syms in file_symbols.items():
                code_ctx.file_symbols[rel_path] = syms
                for sym in syms:
                    code_ctx.symbol_index.setdefault(sym.name, []).append(sym)
            code_ctx.call_graph = call_graph
            code_ctx._rebuild_derived()

        with self._context_lock:
            self._context = code_ctx

        total = code_ctx.total_symbols
        logger.info(
            f"[CIE] Index complete in {elapsed:.2f}s — "
            f"{total} symbols across {len(file_symbols)} files "
            f"({parse_errors} skipped)"
        )
        self._emit_event(code_ctx)

    # ── Dashboard ───────────────────────────────────────────────────

    @staticmethod
    def _emit_event(ctx: CodeContext) -> None:
        try:
            from nova.dashboard.event_bus import emit
            emit(
                "code_indexed",
                module="code_intelligence",
                status="success",
                metadata=ctx.stats(),
            )
        except Exception:
            pass
