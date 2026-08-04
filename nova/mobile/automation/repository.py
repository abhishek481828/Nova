"""AutomationRepository — CRUD + enable/disable/duplicate/export for Routines."""

import uuid
import time
import logging
from typing import List, Optional, Dict, Any
from nova.mobile.automation.models import Routine
from nova.mobile.automation.enums import AutomationStatus

logger = logging.getLogger("nova.mobile.automation.repository")


class AutomationRepository:
    def __init__(self):
        self._routines: Dict[str, Routine] = {}

    def save(self, routine: Routine) -> bool:
        try:
            self._routines[routine.id] = routine
            logger.info(f"Routine saved: '{routine.name}' [{routine.id}]")
            return True
        except Exception as e:
            logger.error(f"Failed to save routine: {e}")
            return False

    def get(self, routine_id: str) -> Optional[Routine]:
        return self._routines.get(routine_id)

    def get_all(self) -> List[Routine]:
        return list(self._routines.values())

    def get_enabled(self) -> List[Routine]:
        return [r for r in self._routines.values() if r.status == AutomationStatus.ENABLED]

    def delete(self, routine_id: str) -> bool:
        if routine_id in self._routines:
            del self._routines[routine_id]
            logger.info(f"Routine deleted: {routine_id}")
            return True
        return False

    def set_status(self, routine_id: str, status: AutomationStatus) -> bool:
        r = self._routines.get(routine_id)
        if not r:
            return False
        r.status = status
        r.updated_at = time.time()
        logger.info(f"Routine '{routine_id}' status → {status.value}")
        return True

    def duplicate(self, routine_id: str) -> Optional[Routine]:
        original = self._routines.get(routine_id)
        if not original:
            return None
        copy = Routine(
            name=f"{original.name} (Copy)",
            trigger=original.trigger,
            actions=original.actions,
            description=original.description,
            conditions=original.conditions,
            status=AutomationStatus.DISABLED,
            routine_id=str(uuid.uuid4())
        )
        self._routines[copy.id] = copy
        logger.info(f"Routine duplicated: '{copy.name}' [{copy.id}]")
        return copy

    def record_execution(self, routine_id: str) -> bool:
        r = self._routines.get(routine_id)
        if not r:
            return False
        r.last_executed_at = time.time()
        r.execution_count += 1
        return True

    def export(self) -> List[Dict[str, Any]]:
        return [
            {"id": r.id, "name": r.name, "description": r.description,
             "status": r.status.value, "execution_count": r.execution_count,
             "created_at": r.created_at, "actions_count": len(r.actions)}
            for r in self._routines.values()
        ]

    def import_routines(self, routines: List[Routine]) -> int:
        count = 0
        for r in routines:
            if self.save(r):
                count += 1
        logger.info(f"Import complete: {count} routines imported")
        return count

    def count(self) -> int:
        return len(self._routines)

    def count_enabled(self) -> int:
        return len(self.get_enabled())
