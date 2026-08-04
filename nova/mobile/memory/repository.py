"""MemoryRepository — CRUD interface over MemoryStore with export/import/search."""

import logging
from typing import List, Optional, Dict, Any
from nova.mobile.memory.enums import MemoryCategory
from nova.mobile.memory.entry import MemoryEntry
from nova.mobile.memory.store import MemoryStore
from nova.mobile.memory.config import MemoryStatistics

logger = logging.getLogger("nova.mobile.memory.repository")


class MemoryRepository:
    def __init__(self, store: MemoryStore):
        self.store = store

    def save(self, entry: MemoryEntry) -> bool:
        ok = self.store.put(entry)
        if ok:
            logger.info(f"Memory saved: [{entry.category.value}] {entry.key} (freq={self.store.get_frequency(entry.category, entry.key)})")
        return ok

    def find(self, category: MemoryCategory, key: str) -> Optional[MemoryEntry]:
        return self.store.get(category, key)

    def list(self, category: Optional[MemoryCategory] = None) -> List[MemoryEntry]:
        return self.store.get_all(category)

    def search(self, query: str) -> List[MemoryEntry]:
        return self.store.search(query)

    def delete(self, category: MemoryCategory, key: str) -> bool:
        ok = self.store.delete(category, key)
        if ok:
            logger.info(f"Memory deleted: [{category.value}] {key}")
        return ok

    def delete_category(self, category: MemoryCategory) -> int:
        count = self.store.delete_category(category)
        logger.info(f"Category cleared: {category.value} ({count} entries)")
        return count

    def clear(self) -> int:
        count = self.store.clear()
        logger.info(f"All memory cleared: {count} entries removed")
        return count

    def export(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.store.get_all()]

    def import_records(self, records: List[MemoryEntry]) -> int:
        imported = 0
        for entry in records:
            if self.store.put(entry):
                imported += 1
        logger.info(f"Memory import complete: {imported} entries imported")
        return imported

    def get_statistics(self) -> MemoryStatistics:
        return MemoryStatistics(
            total_entries=self.store.total_count(),
            entries_by_category=self.store.count_by_category(),
            favorite_contacts_count=len(self.store.get_all(MemoryCategory.FAVORITE_CONTACT)),
            favorite_apps_count=len(self.store.get_all(MemoryCategory.FAVORITE_APP)),
            frequent_commands_count=len(self.store.get_all(MemoryCategory.FREQUENT_COMMAND)),
            recent_commands_count=len(self.store.get_all(MemoryCategory.RECENT_COMMAND))
        )
