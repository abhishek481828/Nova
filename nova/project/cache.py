"""
nova.project.cache
~~~~~~~~~~~~~~~~~~
Disk-persisted metadata cache for ProjectContext.
Stores a JSON snapshot under ~/.config/nova/project_cache.json.
TTL is checked on read; stale entries are silently discarded.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from nova.config import PROJECT_CACHE_PATH
from nova.project.context import ProjectContext

logger = logging.getLogger("nova.project.cache")

# Default cache TTL in seconds (10 minutes)
CACHE_TTL = 600


class ProjectCache:
    """
    Read/write a single ProjectContext to disk.

    The cache is stored as a JSON file keyed by the project root path.
    This means multiple projects can share the same cache file without
    collisions.
    """

    def __init__(self, cache_path: Path = PROJECT_CACHE_PATH) -> None:
        self._path = cache_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self, root: Path, ttl: float = CACHE_TTL) -> Optional[ProjectContext]:
        """
        Load a cached context for *root* if it exists and is fresh.
        Returns None if the cache is absent, stale, or corrupt.
        """
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            entry = raw.get(str(root))
            if not entry:
                return None
            age = time.time() - entry.get("last_scanned", 0)
            if age > ttl:
                logger.debug(f"Cache stale for {root} (age={age:.0f}s > ttl={ttl}s)")
                return None
            ctx = ProjectContext.from_dict(entry)
            logger.debug(f"Cache hit for {root} (age={age:.0f}s)")
            return ctx
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.debug(f"Cache read error: {e}")
            return None

    def save(self, ctx: ProjectContext) -> None:
        """Persist a ProjectContext to the cache file."""
        try:
            # Load existing cache to avoid overwriting other projects
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                raw = {}

            raw[str(ctx.root)] = ctx.to_dict()
            self._path.write_text(
                json.dumps(raw, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.debug(f"Cache saved for {ctx.root}")
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    def invalidate(self, root: Path) -> None:
        """Remove the cached entry for *root*."""
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            raw.pop(str(root), None)
            self._path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        except Exception:
            pass
