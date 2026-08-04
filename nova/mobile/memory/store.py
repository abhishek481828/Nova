"""MemoryStore — In-memory structured memory store with sensitive-key blocking."""

import logging
import time
from typing import Dict, List, Optional
from nova.mobile.memory.enums import MemoryCategory
from nova.mobile.memory.entry import MemoryEntry, BLOCKED_KEYS

logger = logging.getLogger("nova.mobile.memory.store")


class MemoryStore:
    def __init__(self):
        # Dict[MemoryCategory, Dict[key, MemoryEntry]]
        self._store: Dict[MemoryCategory, Dict[str, MemoryEntry]] = {
            cat: {} for cat in MemoryCategory
        }

    def put(self, entry: MemoryEntry) -> bool:
        if entry.is_sensitive():
            logger.error(f"BLOCKED: Sensitive key '{entry.key}' rejected from memory store.")
            return False

        category_map = self._store.setdefault(entry.category, {})
        existing = category_map.get(entry.key)

        if existing:
            existing.value = entry.value
            existing.confidence = entry.confidence
            existing.frequency = existing.frequency + 1
            existing.updated_at = time.time()
        else:
            category_map[entry.key] = entry

        return True

    def get(self, category: MemoryCategory, key: str) -> Optional[MemoryEntry]:
        return self._store.get(category, {}).get(key)

    def get_all(self, category: Optional[MemoryCategory] = None) -> List[MemoryEntry]:
        if category is not None:
            return list(self._store.get(category, {}).values())
        return [entry for cat_map in self._store.values() for entry in cat_map.values()]

    def search(self, query: str) -> List[MemoryEntry]:
        q = query.lower()
        return [e for e in self.get_all() if q in e.key.lower() or q in e.value.lower()]

    def delete(self, category: MemoryCategory, key: str) -> bool:
        return self._store.get(category, {}).pop(key, None) is not None

    def delete_category(self, category: MemoryCategory) -> int:
        count = len(self._store.get(category, {}))
        self._store[category] = {}
        return count

    def clear(self) -> int:
        total = self.total_count()
        for cat in MemoryCategory:
            self._store[cat] = {}
        return total

    def total_count(self) -> int:
        return sum(len(m) for m in self._store.values())

    def count_by_category(self) -> Dict[str, int]:
        return {cat.value: len(m) for cat, m in self._store.items()}

    def get_frequency(self, category: MemoryCategory, key: str) -> int:
        entry = self.get(category, key)
        return entry.frequency if entry else 0
