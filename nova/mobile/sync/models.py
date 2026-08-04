"""Sync Data Models — DeviceInfo, SyncPayload, SyncConflict, SyncSession, SyncStats."""

import uuid
import time
import hashlib
from typing import Optional, Set, Dict
from dataclasses import dataclass, field
from nova.mobile.sync.enums import Platform, DeviceStatus, SyncCategory

# Keys that are NEVER synchronized
BLOCKED_SYNC_KEYS = frozenset({
    "password", "passwd", "otp", "token", "secret",
    "private_key", "auth_token", "access_token", "refresh_token",
    "pin", "cvv", "ssn"
})


@dataclass
class DeviceInfo:
    device_id: str
    device_name: str
    platform: Platform
    version: str
    capabilities: Set[str] = field(default_factory=set)
    last_seen: float = field(default_factory=time.time)
    status: DeviceStatus = DeviceStatus.UNAUTHENTICATED
    is_authenticated: bool = False
    health_score: float = 1.0


@dataclass
class SyncPayload:
    category: SyncCategory
    key: str
    value: str
    source_device_id: str
    payload_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    checksum: str = ""

    def __post_init__(self):
        if not self.checksum:
            self.checksum = hashlib.sha256(self.value.encode()).hexdigest()[:16]

    def is_sensitive(self) -> bool:
        return any(blocked in self.key.lower() for blocked in BLOCKED_SYNC_KEYS)

    def verify_integrity(self) -> bool:
        if not self.checksum:
            return True
        return self.checksum == hashlib.sha256(self.value.encode()).hexdigest()[:16]


@dataclass
class SyncConflict:
    category: SyncCategory
    key: str
    local_value: str
    remote_value: str
    local_timestamp: float
    remote_timestamp: float
    local_device_id: str
    remote_device_id: str
    conflict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    resolved_value: Optional[str] = None
    is_resolved: bool = False
    detected_at: float = field(default_factory=time.time)


@dataclass
class SyncSession:
    origin_device_id: str
    current_device_id: str
    task_description: str
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    context_snapshot: Dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    is_active: bool = True


@dataclass
class SyncStats:
    total_payloads_sent: int = 0
    total_payloads_received: int = 0
    total_conflicts_detected: int = 0
    total_conflicts_resolved: int = 0
    last_sync_timestamp: float = 0.0
    pending_queue_size: int = 0
    connected_devices: int = 0
