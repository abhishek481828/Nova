"""Health Monitor for Nova v2.0 Companion Devices."""

import time
from typing import Dict, List
from nova.companion.devices.device_manager import DeviceManager


class HealthMonitor:
    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager

    def check_health(self) -> Dict[str, dict]:
        """Runs health checks on all registered devices."""
        report = {}
        all_devices = self.device_manager.db.list_devices()
        now = time.time()

        for dev in all_devices:
            is_online = self.device_manager.is_online(dev.device_id)
            telemetry = self.device_manager.get_telemetry(dev.device_id)
            last_seen_delta = now - dev.last_seen

            status = "HEALTHY" if is_online else ("DEGRADED" if last_seen_delta < 120 else "OFFLINE")

            report[dev.device_id] = {
                "name": dev.name,
                "platform": dev.platform,
                "status": status,
                "is_online": is_online,
                "battery_level": telemetry.get("battery_level"),
                "is_charging": telemetry.get("is_charging"),
                "seconds_since_last_seen": round(last_seen_delta, 1)
            }
        return report
