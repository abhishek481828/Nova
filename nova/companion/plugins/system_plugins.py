"""System Action Plugins for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class SMSPlugin(BaseCompanionPlugin):
    @property
    def plugin_name(self) -> str:
        return "system.sms"

    @property
    def supported_actions(self) -> List[str]:
        return ["sms.send", "sms.read"]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "recipient": payload.get("recipient"),
            "message": payload.get("message"),
            "device_id": device_id
        }


class AppLauncherPlugin(BaseCompanionPlugin):
    @property
    def plugin_name(self) -> str:
        return "system.apps"

    @property
    def supported_actions(self) -> List[str]:
        return ["app.launch", "app.list"]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "package_name": payload.get("package_name"),
            "device_id": device_id
        }


class ClipboardPlugin(BaseCompanionPlugin):
    @property
    def plugin_name(self) -> str:
        return "system.clipboard"

    @property
    def supported_actions(self) -> List[str]:
        return ["clipboard.get", "clipboard.set"]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "text": payload.get("text"),
            "device_id": device_id
        }
