"""Clipboard Feature Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class ClipboardPlugin(BaseCompanionPlugin):
    """Plugin handling local device clipboard read, write, and clear operations."""

    def __init__(self):
        self._content = ""

    @property
    def plugin_name(self) -> str:
        return "system.clipboard"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "clipboard.get",
            "clipboard.set",
            "clipboard.clear"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "clipboard.set":
            self._content = payload.get("text", "")
            return {"action": action, "device_id": device_id, "text": self._content, "status": "set"}
        elif action == "clipboard.get":
            return {"action": action, "device_id": device_id, "text": self._content}
        elif action == "clipboard.clear":
            self._content = ""
            return {"action": action, "device_id": device_id, "status": "cleared"}

        return {"action": action, "device_id": device_id, "status": "dispatched"}
