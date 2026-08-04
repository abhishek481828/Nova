"""Hardware Action Plugins for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class FlashlightPlugin(BaseCompanionPlugin):
    @property
    def plugin_name(self) -> str:
        return "hardware.flashlight"

    @property
    def supported_actions(self) -> List[str]:
        return ["flashlight.on", "flashlight.off", "flashlight.toggle"]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        state = "on" if "on" in action or payload.get("enabled") else "off"
        return {"action": action, "state": state, "device_id": device_id}


class BatteryPlugin(BaseCompanionPlugin):
    @property
    def plugin_name(self) -> str:
        return "hardware.battery"

    @property
    def supported_actions(self) -> List[str]:
        return ["battery.get_status"]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"action": action, "device_id": device_id, "query": "requested_status"}


class LocationPlugin(BaseCompanionPlugin):
    @property
    def plugin_name(self) -> str:
        return "hardware.gps"

    @property
    def supported_actions(self) -> List[str]:
        return ["gps.get_location"]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"action": action, "device_id": device_id, "query": "requested_location"}
