"""
nova.project.watcher
~~~~~~~~~~~~~~~~~~~~
Lightweight polling watcher that detects file changes in the project tree
and triggers incremental index updates. No external dependencies required
(falls back gracefully from watchdog to pure polling).
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Set

logger = logging.getLogger("nova.project.watcher")

# ------------------------------------------------------------------ #
# Types                                                                #
# ------------------------------------------------------------------ #

ChangeCallback = Callable[[str, str], None]  # (event_type, path_str)
# event_type ∈ {"added", "modified", "deleted"}

# ------------------------------------------------------------------ #
# Polling watcher                                                       #
# ------------------------------------------------------------------ #

class ProjectWatcher:
    """
    Polls the project root for file-system changes at a configurable interval.

    On each tick it compares the current mtime snapshot against the
    previous one and fires *on_change* for every delta. This approach
    requires zero extra dependencies and works equally well on NixOS,
    macOS, and WSL.
    """

    def __init__(
        self,
        root: Path,
        on_change: ChangeCallback,
        poll_interval: float = 5.0,
        ignored_dirs: Optional[Set[str]] = None,
    ) -> None:
        self.root = root
        self.on_change = on_change
        self.poll_interval = poll_interval
        self._ignored_dirs = ignored_dirs or _default_ignored_dirs()
        self._snapshot: Dict[str, float] = {}  # rel_path → mtime
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---------------------------------------------------------------- #
    # Public interface                                                  #
    # ---------------------------------------------------------------- #

    def start(self) -> None:
        """Start the watcher in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._snapshot = self._take_snapshot()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="ProjectWatcher",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"ProjectWatcher started (interval={self.poll_interval}s) for {self.root}")

    def stop(self) -> None:
        """Stop the watcher thread gracefully."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.poll_interval + 1)
        logger.info("ProjectWatcher stopped.")

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ---------------------------------------------------------------- #
    # Internal                                                          #
    # ---------------------------------------------------------------- #

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as e:
                logger.debug(f"Watcher tick error: {e}")
            self._stop_event.wait(self.poll_interval)

    def _tick(self) -> None:
        new_snapshot = self._take_snapshot()
        old_keys = set(self._snapshot)
        new_keys = set(new_snapshot)

        added   = new_keys - old_keys
        deleted = old_keys - new_keys
        modified = {
            k for k in old_keys & new_keys
            if new_snapshot[k] != self._snapshot[k]
        }

        for path_str in sorted(added):
            self._fire("added", path_str)
        for path_str in sorted(deleted):
            self._fire("deleted", path_str)
        for path_str in sorted(modified):
            self._fire("modified", path_str)

        self._snapshot = new_snapshot

    def _fire(self, event_type: str, path_str: str) -> None:
        logger.debug(f"[Watcher] {event_type}: {path_str}")
        try:
            self.on_change(event_type, path_str)
        except Exception as e:
            logger.warning(f"on_change callback error: {e}")

    def _take_snapshot(self) -> Dict[str, float]:
        """Walk the tree and record mtime for every tracked file."""
        snapshot: Dict[str, float] = {}
        try:
            for entry in _walk(self.root, self._ignored_dirs):
                try:
                    rel = str(entry.relative_to(self.root))
                    snapshot[rel] = entry.stat().st_mtime
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Snapshot walk error: {e}")
        return snapshot


# ------------------------------------------------------------------ #
# Helpers                                                               #
# ------------------------------------------------------------------ #

def _default_ignored_dirs() -> Set[str]:
    from nova.project.indexer import IGNORED_DIRS
    return IGNORED_DIRS


def _walk(root: Path, ignored_dirs: Set[str]):
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            for child in current.iterdir():
                if child.is_dir():
                    if child.name not in ignored_dirs and not child.name.endswith(".egg-info"):
                        stack.append(child)
                elif child.is_file():
                    yield child
        except PermissionError:
            continue
