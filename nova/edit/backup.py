"""
nova.edit.backup
~~~~~~~~~~~~~~~~
BackupManager — creates and manages per-file backups before every edit.

Layout under project root:
    .nova_backup/
        nova/core/memory.py.1720380000.bak
        nova/core/memory.py.1720380060.bak   ← most recent

Rules:
- A backup is taken BEFORE a file is modified (or deleted).
- At most MAX_BACKUPS_PER_FILE backups are kept per file; older ones are pruned.
- The backup directory is excluded from the project index (it starts with '.').
"""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("nova.edit.backup")

# Maximum number of backup copies to keep per file
MAX_BACKUPS_PER_FILE = 10

# Backup directory name (relative to project root)
BACKUP_DIR = ".nova_backup"


class BackupManager:
    """
    Creates timestamped backups of files before they are edited.

    Parameters
    ----------
    project_root : Path
        The root of the project being edited.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.backup_root  = project_root / BACKUP_DIR

    def backup(self, rel_path: str) -> Optional[Path]:
        """
        Copy the current version of *rel_path* to the backup directory.

        Returns the backup file Path on success, None if the file does not
        exist (e.g. backing up before a CREATE operation is unnecessary).
        """
        src = self.project_root / rel_path
        if not src.exists():
            return None

        ts = f"{time.time():.6f}"
        backup_path = self.backup_root / f"{rel_path}.{ts}.bak"
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(src, backup_path)
            logger.debug(f"[Backup] {rel_path} → {backup_path.relative_to(self.project_root)}")
        except Exception as e:
            logger.warning(f"[Backup] Failed to back up {rel_path}: {e}")
            return None

        self._prune(rel_path)
        return backup_path

    def restore(self, rel_path: str) -> Optional[str]:
        """
        Restore the most recent backup for *rel_path*.
        Returns the restored content as a string, or None if no backup exists.
        """
        backups = self._list_backups(rel_path)
        if not backups:
            logger.warning(f"[Backup] No backup found for: {rel_path}")
            return None

        latest = backups[-1]
        try:
            content = latest.read_text(encoding="utf-8", errors="replace")
            logger.debug(f"[Backup] Restored {rel_path} from {latest.name}")
            return content
        except Exception as e:
            logger.warning(f"[Backup] Failed to restore {rel_path}: {e}")
            return None

    def list_backups(self, rel_path: str) -> List[str]:
        """Return a list of backup file names for *rel_path*, oldest first."""
        return [str(p.name) for p in self._list_backups(rel_path)]

    def cleanup_all(self) -> None:
        """Remove the entire backup directory. Use with caution."""
        if self.backup_root.exists():
            shutil.rmtree(self.backup_root)
            logger.info("[Backup] Backup directory removed.")

    # ── Internal ─────────────────────────────────────────────────────

    def _list_backups(self, rel_path: str) -> List[Path]:
        """Return backup paths for *rel_path*, sorted by timestamp ascending."""
        # Glob: replace path separators so we can match nested paths
        safe_prefix = rel_path.replace("/", "_").replace("\\", "_")
        # Search directly — backups mirror the rel_path directory structure
        parent = self.backup_root / Path(rel_path).parent
        if not parent.exists():
            return []
        stem = Path(rel_path).name
        candidates = sorted(
            p for p in parent.iterdir()
            if p.name.startswith(stem + ".") and p.name.endswith(".bak")
        )
        return candidates

    def _prune(self, rel_path: str) -> None:
        """Remove old backups if we exceed MAX_BACKUPS_PER_FILE."""
        backups = self._list_backups(rel_path)
        excess = len(backups) - MAX_BACKUPS_PER_FILE
        if excess > 0:
            for old in backups[:excess]:
                try:
                    old.unlink()
                    logger.debug(f"[Backup] Pruned old backup: {old.name}")
                except Exception:
                    pass
