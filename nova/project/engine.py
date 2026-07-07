"""
nova.project.engine
~~~~~~~~~~~~~~~~~~~
ProjectAwarenessEngine — the singleton orchestrator that drives detection,
indexing, caching, and watching of the active software project.

Usage (from any Nova component):
    from nova.project import get_project_context
    ctx = get_project_context()
    if ctx:
        print(ctx.summary)
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from nova.project.cache import ProjectCache
from nova.project.context import ProjectContext
from nova.project.detector import (
    detect_frameworks,
    detect_git,
    detect_languages,
    detect_project_name,
    find_project_root,
)
from nova.project.indexer import (
    build_index_sync,
    update_index_for_file,
)
from nova.project.manifest import MANIFEST_PARSERS, parse_manifest
from nova.project.watcher import ProjectWatcher

logger = logging.getLogger("nova.project.engine")


class ProjectAwarenessEngine:
    """
    Thread-safe singleton for project detection, indexing, and watching.

    Lifecycle:
        engine = ProjectAwarenessEngine()
        engine.scan(Path.cwd())           # synchronous, blocks until done
        # or:
        engine.scan_in_background(cwd)    # non-blocking daemon thread

        ctx = engine.get_context()        # any thread can call this
        engine.stop()                     # on shutdown
    """

    _instance: Optional["ProjectAwarenessEngine"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "ProjectAwarenessEngine":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialised = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialised:
            return
        self._context: Optional[ProjectContext] = None
        self._context_lock = threading.Lock()
        self._watcher: Optional[ProjectWatcher] = None
        self._cache = ProjectCache()
        self._change_listeners: list = []
        self._initialised = True

    # ---------------------------------------------------------------- #
    # Public API                                                        #
    # ---------------------------------------------------------------- #

    def register_change_listener(self, callback) -> None:
        """
        Register an additional callback for file-change events.
        callback(event_type: str, path_str: str) will be called after the
        file index is updated.  Thread-safe; deduplicates by identity.
        """
        if callback not in self._change_listeners:
            self._change_listeners.append(callback)
            logger.debug(f"Change listener registered: {callback}")

    def get_context(self) -> Optional[ProjectContext]:
        """Return the current ProjectContext, or None if not yet scanned."""
        with self._context_lock:
            return self._context

    def scan(self, directory: Path) -> ProjectContext:
        """
        Perform a full synchronous scan of *directory*.
        Checks cache first; falls back to a fresh scan on miss/expiry.
        """
        root = find_project_root(directory)

        # Try cache first
        cached = self._cache.load(root)
        if cached is not None:
            with self._context_lock:
                self._context = cached
            logger.info(f"Loaded project context from cache: {root}")
            return cached

        ctx = self._full_scan(root)
        with self._context_lock:
            self._context = ctx
        self._cache.save(ctx)
        return ctx

    def scan_in_background(self, directory: Path) -> None:
        """
        Launch a daemon thread to perform the scan without blocking startup.
        """
        t = threading.Thread(
            target=self._bg_scan,
            args=(directory,),
            name="ProjectAwareness-Scan",
            daemon=True,
        )
        t.start()
        logger.info(f"Project awareness scan started in background for: {directory}")

    def start_watching(self) -> None:
        """
        Start the file watcher for the current project root.
        Safe to call before scan completes — watcher starts only after context exists.
        """
        t = threading.Thread(
            target=self._start_watcher_when_ready,
            name="ProjectAwareness-WatchStarter",
            daemon=True,
        )
        t.start()

    def stop(self) -> None:
        """Shut down the watcher and clear the context."""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None
        logger.info("ProjectAwarenessEngine stopped.")

    # ---------------------------------------------------------------- #
    # Internal scan logic                                               #
    # ---------------------------------------------------------------- #

    def _bg_scan(self, directory: Path) -> None:
        try:
            ctx = self.scan(directory)
            logger.info(f"Project awareness ready: {ctx.summary}")
            self._emit_update_event(ctx)
            self._start_watcher(ctx.root)
        except Exception as e:
            logger.error(f"Project awareness scan failed: {e}", exc_info=True)

    def _full_scan(self, root: Path) -> ProjectContext:
        t0 = time.perf_counter()
        logger.info(f"Full project scan starting at: {root}")

        # 1. File index
        index = build_index_sync(root)
        file_paths = list(index.keys())

        # 2. Parse all manifest files found in root
        all_deps: dict = {}
        all_dev_deps: dict = {}
        manifest_name: str = ""
        manifest_version: str = ""

        for manifest_filename in MANIFEST_PARSERS:
            manifest_path = root / manifest_filename
            if manifest_path.exists():
                result = parse_manifest(manifest_path)
                all_deps.update(result.get("dependencies", {}))
                all_dev_deps.update(result.get("dev_dependencies", {}))
                if not manifest_name:
                    manifest_name = result.get("name", "")
                if not manifest_version:
                    manifest_version = result.get("version", "")

        # 3. Language detection
        languages = detect_languages(file_paths)

        # 4. Framework detection
        frameworks = detect_frameworks(root, file_paths, all_deps)

        # 5. Git detection
        is_git, branch, remote = detect_git(root)

        # 6. Project name
        name = detect_project_name(root, {"name": manifest_name})

        elapsed = time.perf_counter() - t0
        total_size = sum(node.size_bytes for node in index.values())

        ctx = ProjectContext(
            root=root,
            name=name,
            languages=languages,
            frameworks=frameworks,
            dependencies=all_deps,
            dev_dependencies=all_dev_deps,
            file_index=index,
            is_git_repo=is_git,
            git_branch=branch,
            git_remote=remote,
            last_scanned=time.time(),
            scan_duration_s=round(elapsed, 3),
            total_files=len(index),
            total_size_bytes=total_size,
            metadata={
                "version": manifest_version,
            },
        )
        logger.info(
            f"Scan complete in {elapsed:.2f}s — {len(index)} files, "
            f"languages: {ctx.all_language_names}, "
            f"frameworks: {frameworks}"
        )
        return ctx

    # ---------------------------------------------------------------- #
    # Watcher                                                           #
    # ---------------------------------------------------------------- #

    def _start_watcher_when_ready(self) -> None:
        """Wait until context is available, then start the watcher."""
        for _ in range(60):  # wait up to 60s
            with self._context_lock:
                ctx = self._context
            if ctx:
                self._start_watcher(ctx.root)
                return
            time.sleep(1)
        logger.warning("ProjectWatcher: timed out waiting for context.")

    def _start_watcher(self, root: Path) -> None:
        if self._watcher and self._watcher.is_running():
            return
        self._watcher = ProjectWatcher(root=root, on_change=self._on_file_change)
        self._watcher.start()

    def _on_file_change(self, event_type: str, path_str: str) -> None:
        """Callback invoked by the watcher on any file change."""
        with self._context_lock:
            ctx = self._context
        if ctx is None:
            return

        full_path = ctx.root / path_str
        update_index_for_file(ctx.file_index, ctx.root, full_path)
        ctx.total_files = len(ctx.file_index)
        ctx.last_scanned = time.time()

        logger.debug(f"Index updated [{event_type}]: {path_str}")
        self._emit_update_event(ctx)

        # Notify secondary listeners (e.g. CodeIntelligenceEngine)
        for listener in list(self._change_listeners):
            try:
                listener(event_type, path_str)
            except Exception as e:
                logger.debug(f"Change listener error: {e}")

    # ---------------------------------------------------------------- #
    # Dashboard integration                                             #
    # ---------------------------------------------------------------- #

    @staticmethod
    def _emit_update_event(ctx: ProjectContext) -> None:
        try:
            from nova.dashboard.event_bus import emit
            emit(
                "project_updated",
                module="project_awareness",
                status="success",
                metadata={
                    "name": ctx.name,
                    "root": str(ctx.root),
                    "languages": ctx.all_language_names,
                    "frameworks": ctx.frameworks,
                    "total_files": ctx.total_files,
                    "git_branch": ctx.git_branch,
                },
            )
        except Exception:
            pass  # Dashboard is optional
