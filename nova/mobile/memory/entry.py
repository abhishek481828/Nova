"""MemoryEntry — Structured personal memory record."""

import uuid
import time
from typing import Optional
from nova.mobile.memory.enums import MemoryCategory

# Keys that are NEVER allowed to be stored
BLOCKED_KEYS = {
    "password", "passwd", "otp", "token", "secret", "pin",
    "card_number", "bank", "cvv", "ssn", "auth_token",
    "access_token", "refresh_token"
}


class MemoryEntry:
    def __init__(
        self,
        category: MemoryCategory,
        key: str,
        value: str,
        confidence: float = 1.0,
        source: str = "auto",
        frequency: int = 1,
        created_at: Optional[float] = None,
        updated_at: Optional[float] = None,
        is_user_editable: bool = True,
        is_user_deletable: bool = True,
        entry_id: Optional[str] = None
    ):
        self.id = entry_id or str(uuid.uuid4())
        self.category = category
        self.key = key
        self.value = value
        self.confidence = min(1.0, max(0.0, confidence))
        self.source = source
        self.frequency = frequency
        self.created_at = created_at or time.time()
        self.updated_at = updated_at or time.time()
        self.is_user_editable = is_user_editable
        self.is_user_deletable = is_user_deletable

    def is_sensitive(self) -> bool:
        return any(blocked in self.key.lower() for blocked in BLOCKED_KEYS)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category.value,
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "frequency": self.frequency,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
