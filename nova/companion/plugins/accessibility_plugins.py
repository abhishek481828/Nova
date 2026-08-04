"""Accessibility Automation Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class AccessibilityPlugin(BaseCompanionPlugin):
    """Plugin handling screen hierarchy inspection, click, scroll, type, and global navigation actions."""

    @property
    def plugin_name(self) -> str:
        return "system.accessibility"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "accessibility.dump_tree",
            "accessibility.click",
            "accessibility.type",
            "accessibility.scroll",
            "accessibility.global_action"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        target = payload.get("view_id") or payload.get("node_id") or payload.get("text")
        return {
            "action": action,
            "target": target,
            "device_id": device_id,
            "status": "dispatched"
        }
