"""Screen Sharing & Remote Touch Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class ScreenPlugin(BaseCompanionPlugin):
    """Plugin handling MediaProjection live screen streaming, remote touch tap, remote keyboard, and screenshots."""

    @property
    def plugin_name(self) -> str:
        return "media.screen"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "screen.capture_screenshot",
            "screen.record_video",
            "screen.start_stream",
            "screen.stop_stream",
            "screen.tap",
            "screen.type"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "device_id": device_id,
            "coordinates": {"x": payload.get("x"), "y": payload.get("y")} if "tap" in action else None,
            "text": payload.get("text") if "type" in action else None,
            "status": "dispatched"
        }
