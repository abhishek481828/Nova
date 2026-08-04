"""Device Info & Telemetry Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class DeviceInfoPlugin(BaseCompanionPlugin):
    """Plugin handling device specifications, telemetry (battery, storage, RAM), and Wi-Fi info."""

    @property
    def plugin_name(self) -> str:
        return "hardware.device_info"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "device.get_info",
            "device.get_telemetry",
            "wifi.get_info"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "device_id": device_id,
            "status": "query_dispatched"
        }
