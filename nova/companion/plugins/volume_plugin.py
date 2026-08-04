"""Volume Feature Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class VolumePlugin(BaseCompanionPlugin):
    """Plugin handling volume get, set, increase, decrease, mute operations."""

    @property
    def plugin_name(self) -> str:
        return "hardware.volume"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "volume.get",
            "volume.set",
            "volume.increase",
            "volume.decrease",
            "volume.mute"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        vol_level = payload.get("level", payload.get("percent", 50))
        return {
            "action": action,
            "device_id": device_id,
            "stream": payload.get("stream", "media"),
            "percent": payload.get("percent", vol_level),
            "volume_level": vol_level,
            "status": "dispatched"
        }
