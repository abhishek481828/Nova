"""Flashlight Feature Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class FlashlightPlugin(BaseCompanionPlugin):
    """Plugin handling phone flashlight control (on, off, toggle, status)."""

    @property
    def plugin_name(self) -> str:
        return "hardware.flashlight"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "flashlight.on",
            "flashlight.off",
            "flashlight.toggle",
            "flashlight.status"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        state = "on" if "on" in action else ("off" if "off" in action else "toggled")
        return {
            "action": action,
            "device_id": device_id,
            "state": state,
            "status": "dispatched"
        }
