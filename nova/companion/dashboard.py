"""Phase I: Real-time Device Monitoring Dashboard & Event System for Nova v2.0."""

import time
import logging
from typing import Dict, Any, List, Optional
from nova.companion.events.event_bus import EventBus
from nova.companion.protocol.schemas import EventMessage

global_event_bus = EventBus()

logger = logging.getLogger("nova.companion.dashboard")


class RealtimeDashboardManager:
    """Aggregates device health, system metrics, and fires event bus alerts."""

    def __init__(self):
        self.connected_devices: Dict[str, Dict[str, Any]] = {}
        self.adb_connected: bool = True
        self.companion_status: str = "ACTIVE"
        self.voice_session_active: bool = False
        self.last_update_ts: float = time.time()

    def _emit_event(self, event_name: str, payload: Dict[str, Any], device_id: str = "nova-core"):
        try:
            msg = EventMessage(event=event_name, payload=payload, source=device_id)
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(global_event_bus.publish(msg))
            except RuntimeError:
                asyncio.run(global_event_bus.publish(msg))
        except Exception as e:
            logger.debug(f"Event emission error: {e}")

    def update_device_state(self, device_id: str, state_data: Dict[str, Any]) -> Dict[str, Any]:
        self.connected_devices[device_id] = state_data
        self.last_update_ts = time.time()

        # Check for warnings and emit EventBus events (Step 9)
        batt_level = state_data.get("battery", {}).get("level", 100)
        if batt_level < 15:
            self._emit_event("Battery Warning", {
                "device_id": device_id,
                "battery_level": batt_level,
                "message": f"Battery low ({batt_level}%)"
            }, device_id)

        stor_pct = state_data.get("storage", {}).get("used_percent", 0.0)
        if stor_pct > 90.0:
            self._emit_event("Storage Warning", {
                "device_id": device_id,
                "storage_used_percent": stor_pct,
                "message": f"Storage nearly full ({stor_pct:.1f}% used)"
            }, device_id)

        cpu_threads = state_data.get("performance", {}).get("active_threads", 0)
        if cpu_threads > 150:
            self._emit_event("Performance Warning", {
                "device_id": device_id,
                "active_threads": cpu_threads,
                "message": f"High thread count load detected ({cpu_threads} threads)"
            }, device_id)

        return self.get_dashboard_summary()

    def register_device_connected(self, device_id: str, details: Dict[str, Any]):
        self.connected_devices[device_id] = details
        self._emit_event("Device Connected", {"device_id": device_id, "details": details}, device_id)

    def register_device_disconnected(self, device_id: str):
        if device_id in self.connected_devices:
            del self.connected_devices[device_id]
        self._emit_event("Device Disconnected", {"device_id": device_id}, device_id)

    def set_adb_status(self, connected: bool):
        self.adb_connected = connected
        event_name = "ADB Connected" if connected else "ADB Disconnected"
        self._emit_event(event_name, {"adb_connected": connected})

    def get_dashboard_summary(self) -> Dict[str, Any]:
        dev_count = len(self.connected_devices)
        primary_dev = list(self.connected_devices.values())[0] if dev_count > 0 else {}
        
        return {
            "connected_devices_count": dev_count,
            "connected_devices": list(self.connected_devices.keys()),
            "device_health": primary_dev.get("health", {"status": "GOOD", "health_score": 90}),
            "battery": primary_dev.get("battery", {"level": 85, "is_charging": False}),
            "cpu": primary_dev.get("cpu", {"cores": 8, "architecture": "aarch64"}),
            "ram": primary_dev.get("memory", {"available_mb": 3500.0, "total_mb": 8000.0}),
            "storage": primary_dev.get("storage", {"free_gb": 45.0, "total_gb": 128.0}),
            "network": primary_dev.get("network", {"transport": "WIFI", "is_connected": True}),
            "adb_status": "CONNECTED" if self.adb_connected else "DISCONNECTED",
            "companion_status": self.companion_status,
            "voice_session_status": "ACTIVE" if self.voice_session_active else "IDLE",
            "timestamp": self.last_update_ts
        }


# Global Singleton Dashboard Instance
global_monitoring_dashboard = RealtimeDashboardManager()
