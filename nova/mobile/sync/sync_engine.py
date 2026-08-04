"""SyncEngine — Builds outbound payloads and applies inbound with integrity checks."""

import time
import hashlib
import logging
from typing import List, Optional
from nova.mobile.sync.models import SyncPayload, BLOCKED_SYNC_KEYS
from nova.mobile.sync.enums import SyncCategory
from nova.mobile.sync.repository import SyncRepository

logger = logging.getLogger("nova.mobile.sync.engine")


class SyncEngine:
    def __init__(self, device_id: str, memory_manager=None, automation_manager=None):
        self.device_id = device_id
        self.memory_manager = memory_manager
        self.automation_manager = automation_manager

    def build_outbound_payloads(self) -> List[SyncPayload]:
        payloads = []

        if self.memory_manager:
            from nova.mobile.memory.enums import MemoryCategory

            # Preferences
            pref_cats = [
                MemoryCategory.PREFERRED_BRIGHTNESS, MemoryCategory.PREFERRED_VOLUME,
                MemoryCategory.PREFERRED_LANGUAGE, MemoryCategory.PREFERRED_MUSIC_APP,
                MemoryCategory.PREFERRED_BROWSER
            ]
            for cat in pref_cats:
                for entry in self.memory_manager.repository.list(cat):
                    if not self.is_sensitive(entry.key):
                        payloads.append(self._make(SyncCategory.PREFERENCES,
                                                   f"{cat.value}:{entry.key}", entry.value))

            # Favorite contacts
            for entry in self.memory_manager.repository.list(MemoryCategory.FAVORITE_CONTACT):
                payloads.append(self._make(SyncCategory.FAVORITE_CONTACTS, entry.key, entry.value))

            # Favorite apps
            for entry in self.memory_manager.repository.list(MemoryCategory.FAVORITE_APP):
                payloads.append(self._make(SyncCategory.FAVORITE_APPS, entry.key, entry.value))

            # Recent commands (last 20 only)
            for entry in self.memory_manager.repository.list(MemoryCategory.RECENT_COMMAND)[-20:]:
                payloads.append(self._make(SyncCategory.RECENT_COMMANDS, entry.key, entry.value))

        if self.automation_manager:
            for routine in self.automation_manager.repository.get_enabled():
                summary = f"{routine.name}|{len(routine.actions)}|{routine.trigger.type.value}"
                payloads.append(self._make(SyncCategory.ROUTINE_DEFINITIONS, routine.id, summary))

        logger.info(f"Built {len(payloads)} outbound sync payloads")
        return payloads

    def apply_inbound(self, payload: SyncPayload, repository: SyncRepository) -> bool:
        if payload.is_sensitive():
            logger.error(f"BLOCKED inbound payload with sensitive key: '{payload.key}'")
            return False

        if not payload.verify_integrity():
            logger.error(f"Integrity FAILED for payload: {payload.payload_id}")
            return False

        return repository.put(payload)

    def is_sensitive(self, key: str) -> bool:
        return any(blocked in key.lower() for blocked in BLOCKED_SYNC_KEYS)

    def _make(self, category: SyncCategory, key: str, value: str) -> SyncPayload:
        return SyncPayload(
            category=category,
            key=key,
            value=value,
            source_device_id=self.device_id,
            timestamp=time.time()
        )
