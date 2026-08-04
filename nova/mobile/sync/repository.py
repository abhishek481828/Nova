"""SyncRepository — Stores sync state, offline queue, conflicts, and sessions."""

import time
import logging
from collections import deque
from typing import Dict, List, Optional
from nova.mobile.sync.models import SyncPayload, SyncConflict, SyncSession
from nova.mobile.sync.enums import SyncCategory

logger = logging.getLogger("nova.mobile.sync.repository")

MAX_QUEUE_SIZE = 500
MAX_CONFLICT_HISTORY = 200


class SyncRepository:
    def __init__(self):
        # category → key → SyncPayload
        self._state: Dict[SyncCategory, Dict[str, SyncPayload]] = {
            cat: {} for cat in SyncCategory
        }
        self._offline_queue: deque = deque(maxlen=MAX_QUEUE_SIZE)
        self._conflicts: List[SyncConflict] = []
        self._sessions: Dict[str, SyncSession] = {}

    # ── Sync State ────────────────────────────────────────────────────────────

    def put(self, payload: SyncPayload) -> bool:
        existing = self._state.get(payload.category, {}).get(payload.key)
        if existing and payload.timestamp < existing.timestamp:
            return False  # older — caller should handle as conflict
        self._state.setdefault(payload.category, {})[payload.key] = payload
        return True

    def get(self, category: SyncCategory, key: str) -> Optional[SyncPayload]:
        return self._state.get(category, {}).get(key)

    def get_all(self, category: Optional[SyncCategory] = None) -> List[SyncPayload]:
        if category:
            return list(self._state.get(category, {}).values())
        return [p for cat_map in self._state.values() for p in cat_map.values()]

    def detect_conflict(self, incoming: SyncPayload) -> Optional[SyncConflict]:
        existing = self._state.get(incoming.category, {}).get(incoming.key)
        if not existing:
            return None
        if existing.value == incoming.value:
            return None
        if existing.source_device_id == incoming.source_device_id:
            return None
        return SyncConflict(
            category=incoming.category,
            key=incoming.key,
            local_value=existing.value,
            remote_value=incoming.value,
            local_timestamp=existing.timestamp,
            remote_timestamp=incoming.timestamp,
            local_device_id=existing.source_device_id,
            remote_device_id=incoming.source_device_id
        )

    def total_count(self) -> int:
        return sum(len(m) for m in self._state.values())

    # ── Offline Queue ─────────────────────────────────────────────────────────

    def enqueue(self, payload: SyncPayload) -> bool:
        self._offline_queue.append(payload)
        return True

    def drain_queue(self) -> List[SyncPayload]:
        drained = list(self._offline_queue)
        self._offline_queue.clear()
        logger.info(f"Drained {len(drained)} payloads from offline queue")
        return drained

    def queue_size(self) -> int:
        return len(self._offline_queue)

    # ── Conflicts ─────────────────────────────────────────────────────────────

    def record_conflict(self, conflict: SyncConflict):
        self._conflicts.append(conflict)
        if len(self._conflicts) > MAX_CONFLICT_HISTORY:
            self._conflicts.pop(0)

    def get_conflicts(self) -> List[SyncConflict]:
        return list(self._conflicts)

    def get_unresolved(self) -> List[SyncConflict]:
        return [c for c in self._conflicts if not c.is_resolved]

    # ── Sessions ──────────────────────────────────────────────────────────────

    def save_session(self, session: SyncSession):
        self._sessions[session.session_id] = session

    def get_session(self, session_id: str) -> Optional[SyncSession]:
        return self._sessions.get(session_id)

    def get_active_sessions(self) -> List[SyncSession]:
        return [s for s in self._sessions.values() if s.is_active]

    def close_session(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if not s:
            return False
        s.is_active = False
        s.updated_at = time.time()
        return True
