"""Vibration Feature Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class VibrationPlugin(BaseCompanionPlugin):
    """Plugin handling haptic vibration patterns."""

    @property
    def plugin_name(self) -> str:
        return "hardware.vibration"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "vibration.vibrate",
            "vibration.short",
            "vibration.medium",
            "vibration.long",
            "vibration.custom"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "device_id": device_id,
            "duration_ms": payload.get("duration_ms", 300),
            "status": "dispatched"
        }
