"""Gallery & Media Storage Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class GalleryPlugin(BaseCompanionPlugin):
    """Plugin handling MediaStore gallery listing, recent photo retrieval, image fetch, and media upload."""

    @property
    def plugin_name(self) -> str:
        return "media.gallery"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "gallery.list",
            "gallery.get_recent",
            "gallery.fetch",
            "media.upload"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "device_id": device_id,
            "limit": payload.get("limit", 10),
            "media_id": payload.get("media_id"),
            "status": "dispatched"
        }
