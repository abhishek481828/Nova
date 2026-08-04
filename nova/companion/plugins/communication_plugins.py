"""Communication Feature Plugins (SMS, Calls, Contacts) for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin


class CallPlugin(BaseCompanionPlugin):
    """Plugin handling phone calls (make, end, history, status, missed)."""

    @property
    def plugin_name(self) -> str:
        return "communication.calls"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "call.make",
            "call.end",
            "call.history",
            "call.status",
            "call.missed"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "device_id": device_id,
            "number": payload.get("number"),
            "status": "dispatched"
        }


class ContactsPlugin(BaseCompanionPlugin):
    """Plugin handling contacts query and search operations."""

    @property
    def plugin_name(self) -> str:
        return "communication.contacts"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "contacts.list",
            "contacts.search",
            "contacts.details"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "device_id": device_id,
            "query": payload.get("query", ""),
            "status": "dispatched"
        }
