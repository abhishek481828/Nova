"""DeviceRegistry — Trusted device management with authentication and audit logging."""

import time
import logging
from typing import List, Optional, Dict
from nova.mobile.sync.models import DeviceInfo
from nova.mobile.sync.enums import DeviceStatus

logger = logging.getLogger("nova.mobile.sync.device_registry")


class DeviceRegistry:
    def __init__(self):
        self._devices: Dict[str, DeviceInfo] = {}
        self._audit_log: List[str] = []

    def register(self, device: DeviceInfo) -> bool:
        try:
            self._devices[device.device_id] = device
            self._audit(f"REGISTERED device='{device.device_name}' platform={device.platform.value} id={device.device_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to register device: {e}")
            return False

    def authenticate(self, device_id: str) -> bool:
        d = self._devices.get(device_id)
        if not d:
            return False
        d.is_authenticated = True
        d.status = DeviceStatus.AUTHENTICATED
        d.last_seen = time.time()
        self._audit(f"AUTHENTICATED device='{d.device_name}' id={device_id}")
        return True

    def revoke(self, device_id: str) -> bool:
        d = self._devices.get(device_id)
        if not d:
            return False
        d.is_authenticated = False
        d.status = DeviceStatus.UNAUTHENTICATED
        self._audit(f"REVOKED device='{d.device_name}' id={device_id}")
        return True

    def update_heartbeat(self, device_id: str):
        d = self._devices.get(device_id)
        if d:
            d.last_seen = time.time()
            d.status = DeviceStatus.ONLINE

    def mark_offline(self, device_id: str):
        d = self._devices.get(device_id)
        if d:
            d.status = DeviceStatus.OFFLINE
            self._audit(f"OFFLINE device='{d.device_name}' id={device_id}")

    def get(self, device_id: str) -> Optional[DeviceInfo]:
        return self._devices.get(device_id)

    def get_all(self) -> List[DeviceInfo]:
        return list(self._devices.values())

    def get_authenticated(self) -> List[DeviceInfo]:
        return [d for d in self._devices.values() if d.is_authenticated]

    def get_online(self) -> List[DeviceInfo]:
        return [d for d in self._devices.values()
                if d.is_authenticated and d.status == DeviceStatus.ONLINE]

    def is_authenticated(self, device_id: str) -> bool:
        return self._devices.get(device_id, DeviceInfo("", "", None, "")).is_authenticated

    def remove(self, device_id: str) -> bool:
        d = self._devices.pop(device_id, None)
        if d:
            self._audit(f"REMOVED device='{d.device_name}' id={device_id}")
        return d is not None

    def get_audit_log(self) -> List[str]:
        return list(self._audit_log)

    def count(self) -> int:
        return len(self._devices)

    def count_online(self) -> int:
        return len(self.get_online())

    def _audit(self, message: str):
        entry = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {message}"
        self._audit_log.append(entry)
        logger.info(entry)
        if len(self._audit_log) > 500:
            self._audit_log.pop(0)
