"""MemoryManager — Phase 6 orchestrator: learning, queries, privacy, events."""

import time
import logging
from typing import Optional, List
from collections import deque

from nova.mobile.memory.enums import MemoryCategory, MemoryEvent
from nova.mobile.memory.entry import MemoryEntry
from nova.mobile.memory.store import MemoryStore
from nova.mobile.memory.repository import MemoryRepository
from nova.mobile.memory.config import MemoryConfiguration

logger = logging.getLogger("nova.mobile.memory.manager")

# Memory query trigger phrases
RECALL_TRIGGERS = [
    "what do you remember", "what you know about me",
    "show my memories", "show remembered", "my preferences"
]
FORGET_ALL_TRIGGERS = ["forget everything", "clear all memory", "delete everything"]
FORGET_CONTACTS_TRIGGERS = ["forget my contacts", "forget favorite contacts", "forget my favorite contacts"]
FORGET_APPS_TRIGGERS = ["forget my apps", "forget favorite apps"]
FORGET_COMMANDS_TRIGGERS = ["clear recent commands", "forget recent commands"]
FORGET_ROUTINES_TRIGGERS = ["forget my routines", "forget routines"]


class MemoryManager:
    def __init__(self, config: Optional[MemoryConfiguration] = None, lifecycle_manager=None):
        self.config = config or MemoryConfiguration()
        self.lifecycle_manager = lifecycle_manager
        self.store = MemoryStore()
        self.repository = MemoryRepository(self.store)

        # Internal frequency counters
        self._contact_freq: dict = {}
        self._app_freq: dict = {}
        self._brightness_history: List[int] = []
        self._volume_history: List[int] = []
        self._recent_buffer: deque = deque(maxlen=self.config.max_recent_commands)

    # ── Command Learning ──────────────────────────────────────────────────────

    def on_command_executed(self, intent: str, entities: dict, raw_text: str = ""):
        """Called after every successful command execution."""
        self._track_recent(raw_text or intent)
        if self.config.auto_learn_contacts:
            self._learn_contact(intent, entities)
        if self.config.auto_learn_apps:
            self._learn_app(intent, entities, raw_text)
        if self.config.auto_learn_preferences:
            self._learn_preferences(intent, entities)

    def _track_recent(self, raw_text: str):
        self._recent_buffer.append(raw_text)
        entry = MemoryEntry(
            category=MemoryCategory.RECENT_COMMAND,
            key=f"recent_{int(time.time()*1000)}",
            value=raw_text
        )
        self.repository.save(entry)

        # Promote to frequent command if threshold met
        low = raw_text.lower().strip()
        existing_freq = self.store.get_frequency(MemoryCategory.FREQUENT_COMMAND, low)
        freq = existing_freq + 1
        if freq >= self.config.command_frequency_threshold:
            frequent = MemoryEntry(
                category=MemoryCategory.FREQUENT_COMMAND,
                key=low,
                value=raw_text,
                confidence=min(1.0, freq * 0.1),
                frequency=freq
            )
            is_new = self.store.get(MemoryCategory.FREQUENT_COMMAND, low) is None
            if self.repository.save(frequent):
                self._publish(MemoryEvent.MEMORY_CREATED if is_new else MemoryEvent.MEMORY_UPDATED,
                              "FREQUENT_COMMAND", low)

    def _learn_contact(self, intent: str, entities: dict):
        if intent not in ("CALL_CONTACT", "SEND_SMS"):
            return
        name = entities.get("contact_name") or entities.get("name")
        if not name:
            return
        freq = self._contact_freq.get(name, 0) + 1
        self._contact_freq[name] = freq

        if freq >= self.config.contact_frequency_threshold:
            is_new = self.store.get(MemoryCategory.FAVORITE_CONTACT, name.lower()) is None
            entry = MemoryEntry(
                category=MemoryCategory.FAVORITE_CONTACT,
                key=name.lower(),
                value=name,
                frequency=freq,
                confidence=min(1.0, freq * 0.1),
                source="auto"
            )
            if self.repository.save(entry):
                logger.info(f"Favorite contact learned: {name} (freq={freq})")
                self._publish(MemoryEvent.MEMORY_CREATED if is_new else MemoryEvent.MEMORY_UPDATED,
                              "FAVORITE_CONTACT", name)

    def _learn_app(self, intent: str, entities: dict, raw_text: str):
        app_intents = {"OPEN_APP", "PLAY_YOUTUBE", "PLAY_SPOTIFY", "OPEN_BROWSER", "OPEN_MAPS"}
        if intent not in app_intents:
            return
        app_name = entities.get("app_name") or self._extract_app_hint(raw_text)
        if not app_name:
            return
        freq = self._app_freq.get(app_name, 0) + 1
        self._app_freq[app_name] = freq

        if freq >= self.config.app_frequency_threshold:
            is_new = self.store.get(MemoryCategory.FAVORITE_APP, app_name.lower()) is None
            entry = MemoryEntry(
                category=MemoryCategory.FAVORITE_APP,
                key=app_name.lower(),
                value=app_name,
                frequency=freq,
                confidence=min(1.0, freq * 0.1),
                source="auto"
            )
            if self.repository.save(entry):
                logger.info(f"Favorite app learned: {app_name} (freq={freq})")
                self._publish(MemoryEvent.MEMORY_CREATED if is_new else MemoryEvent.MEMORY_UPDATED,
                              "FAVORITE_APP", app_name)

    def _learn_preferences(self, intent: str, entities: dict):
        if intent == "SET_BRIGHTNESS":
            pct = self._parse_int(entities.get("percentage"))
            if pct is not None:
                self._brightness_history.append(pct)
                if len(self._brightness_history) >= self.config.preference_repeat_threshold:
                    avg = int(sum(self._brightness_history[-5:]) / min(5, len(self._brightness_history)))
                    entry = MemoryEntry(
                        category=MemoryCategory.PREFERRED_BRIGHTNESS,
                        key="preferred_brightness",
                        value=str(avg),
                        confidence=0.85,
                        frequency=len(self._brightness_history),
                        source="auto"
                    )
                    if self.repository.save(entry):
                        logger.info(f"Preferred brightness learned: {avg}%")
                        self._publish(MemoryEvent.MEMORY_UPDATED, "PREFERRED_BRIGHTNESS", str(avg))

        elif intent == "SET_VOLUME":
            pct = self._parse_int(entities.get("percentage"))
            if pct is not None:
                self._volume_history.append(pct)
                if len(self._volume_history) >= self.config.preference_repeat_threshold:
                    avg = int(sum(self._volume_history[-5:]) / min(5, len(self._volume_history)))
                    entry = MemoryEntry(
                        category=MemoryCategory.PREFERRED_VOLUME,
                        key="preferred_volume",
                        value=str(avg),
                        confidence=0.85,
                        frequency=len(self._volume_history),
                        source="auto"
                    )
                    if self.repository.save(entry):
                        logger.info(f"Preferred volume learned: {avg}%")
                        self._publish(MemoryEvent.MEMORY_UPDATED, "PREFERRED_VOLUME", str(avg))

    # ── Memory Query Handler ──────────────────────────────────────────────────

    def handle_memory_query(self, raw_text: str) -> Optional[str]:
        clean = raw_text.lower().strip()

        if any(t in clean for t in RECALL_TRIGGERS):
            return self._build_recall_response()
        if any(t in clean for t in FORGET_ALL_TRIGGERS):
            return self._forget_all()
        if any(t in clean for t in FORGET_CONTACTS_TRIGGERS):
            return self._forget_category(MemoryCategory.FAVORITE_CONTACT, "favorite contacts")
        if any(t in clean for t in FORGET_APPS_TRIGGERS):
            return self._forget_category(MemoryCategory.FAVORITE_APP, "favorite apps")
        if any(t in clean for t in FORGET_COMMANDS_TRIGGERS):
            return self._forget_category(MemoryCategory.RECENT_COMMAND, "recent commands")
        if any(t in clean for t in FORGET_ROUTINES_TRIGGERS):
            return self._forget_category(MemoryCategory.DAILY_ROUTINE, "routines")
        return None

    def _build_recall_response(self) -> str:
        stats = self.repository.get_statistics()
        contacts = [e.value for e in self.repository.list(MemoryCategory.FAVORITE_CONTACT)[:5]]
        apps = [e.value for e in self.repository.list(MemoryCategory.FAVORITE_APP)[:5]]
        brightness = self.store.get(MemoryCategory.PREFERRED_BRIGHTNESS, "preferred_brightness")
        volume = self.store.get(MemoryCategory.PREFERRED_VOLUME, "preferred_volume")

        lines = ["Here's what I remember about you:"]
        if contacts:
            lines.append(f"• Favorite Contacts: {', '.join(contacts)}")
        if apps:
            lines.append(f"• Favorite Apps: {', '.join(apps)}")
        if brightness:
            lines.append(f"• Preferred Brightness: {brightness.value}%")
        if volume:
            lines.append(f"• Preferred Volume: {volume.value}%")
        lines.append(f"• Total Memories: {stats.total_entries}")
        if stats.total_entries == 0:
            lines.append("I haven't learned much yet. Keep using Nova!")
        return "\n".join(lines)

    def _forget_category(self, category: MemoryCategory, label: str) -> str:
        count = self.repository.delete_category(category)
        self._publish(MemoryEvent.MEMORY_DELETED, category.value, "all")
        return f"Done. I've forgotten your {label} ({count} items removed)." if count > 0 \
            else f"I didn't have any {label} stored."

    def _forget_all(self) -> str:
        count = self.repository.clear()
        self._contact_freq.clear()
        self._app_freq.clear()
        self._brightness_history.clear()
        self._volume_history.clear()
        self._recent_buffer.clear()
        self._publish(MemoryEvent.MEMORY_CLEARED, "ALL", "all")
        return f"Done. I've securely cleared all {count} stored memories."

    # ── Sync ─────────────────────────────────────────────────────────────────

    def sync_with_nova_core(self) -> bool:
        if not self.config.sync_with_nova_core:
            logger.info("Nova Core sync disabled by user config.")
            return False
        logger.info("Syncing memory with Nova Core...")
        self._publish(MemoryEvent.MEMORY_SYNCHRONIZED, "ALL", "sync_requested")
        return True

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_app_hint(self, raw_text: str) -> Optional[str]:
        text = raw_text.lower()
        for name, kw in [("YouTube", "youtube"), ("Spotify", "spotify"),
                         ("Chrome", "chrome"), ("Google Maps", "maps"),
                         ("Camera", "camera"), ("Gallery", "gallery")]:
            if kw in text:
                return name
        return None

    def _parse_int(self, val) -> Optional[int]:
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    def _publish(self, event: MemoryEvent, category: str, key: str):
        if self.lifecycle_manager:
            self.lifecycle_manager.publish_event(
                event.value,
                {"category": category, "key": key, "timestamp": time.time()}
            )
