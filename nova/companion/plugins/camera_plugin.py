"""Camera & Media Capture Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class CameraPlugin(BaseCompanionPlugin):
    """Plugin handling CameraX capture, video recording, QR scanning, and OCR text recognition."""

    @property
    def plugin_name(self) -> str:
        return "media.camera"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "camera.capture_photo",
            "camera.record_video",
            "camera.scan_qr",
            "camera.ocr_scan"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        camera_facing = payload.get("camera_selector", "back")
        quality = payload.get("quality", 90)

        return {
            "action": action,
            "device_id": device_id,
            "camera_facing": camera_facing,
            "quality": quality,
            "status": "dispatched"
        }
