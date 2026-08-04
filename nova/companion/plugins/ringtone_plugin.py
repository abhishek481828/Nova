"""Ringtone Control Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class RingtonePlugin(BaseCompanionPlugin):
    @property
    def plugin_name(self) -> str:
        return "hardware.ringtone"

    @property
    def supported_actions(self) -> List[str]:
        return ["ringtone.play", "ringtone.stop"]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "device_id": device_id,
            "status": "playing" if action == "ringtone.play" else "stopped"
        }
