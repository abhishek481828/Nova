"""Centralized Device Manager for Nova v2.0."""

import time
from typing import Dict, List, Optional
from nova.companion.storage.db import CompanionDatabase
from nova.companion.storage.models import DeviceRecord
from nova.companion.protocol.schemas import HeartbeatMessage


class DeviceManager:
    """Tracks connected devices, online/offline status, battery levels, and capabilities."""

    def __init__(self, db: Optional[CompanionDatabase] = None):
        self.db = db or CompanionDatabase()
        # In-memory runtime state
        self._online_devices: Dict[str, float] = {}  # device_id -> last_heartbeat_timestamp
        self._device_telemetry: Dict[str, dict] = {} # device_id -> telemetry stats

    def register_or_update_device(
        self,
        device_id: str,
        name: str,
        platform: str,
        capabilities: List[str],
        protocol_version: str = "2.0"
    ) -> DeviceRecord:
        record = self.db.get_device(device_id)
        now = time.time()
        if record:
            record.name = name
            record.platform = platform
            record.capabilities = capabilities
            record.protocol_version = protocol_version
            record.last_seen = now
        else:
            record = DeviceRecord(
                device_id=device_id,
                name=name,
                platform=platform,
                capabilities=capabilities,
                protocol_version=protocol_version,
                created_at=now,
                last_seen=now
            )
        self.db.save_device(record)
        self._online_devices[device_id] = now
        return record

    def get_device(self, device_id: str) -> Optional[DeviceRecord]:
        return self.db.get_device(device_id)

    def record_heartbeat(self, hb: HeartbeatMessage):
        now = time.time()
        self._online_devices[hb.device_id] = now
        self._device_telemetry[hb.device_id] = {
            "battery_level": hb.battery_level,
            "is_charging": hb.is_charging,
            "status": hb.status,
            "last_heartbeat": now
        }
        # Update DB last_seen
        device = self.db.get_device(hb.device_id)
        if device:
            device.last_seen = now
            self.db.save_device(device)

    def is_online(self, device_id: str, timeout_seconds: float = 45.0) -> bool:
        last_seen = self._online_devices.get(device_id)
        if not last_seen:
            return False
        return (time.time() - last_seen) <= timeout_seconds

    def mark_offline(self, device_id: str):
        self._online_devices.pop(device_id, None)

    def list_online_devices(self) -> List[DeviceRecord]:
        online_list = []
        for device in self.db.list_devices():
            if self.is_online(device.device_id):
                online_list.append(device)
        return online_list

    def get_telemetry(self, device_id: str) -> dict:
        return self._device_telemetry.get(device_id, {})
