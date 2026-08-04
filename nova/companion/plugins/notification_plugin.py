"""Notification & Interception Plugin for Nova v2.0."""

from typing import Any, Dict, List, Optional
import logging
from nova.companion.plugins.base_plugin import BaseCompanionPlugin
from nova.companion.protocol.schemas import EventMessage

logger = logging.getLogger("nova.companion.plugins.notification")


class NotificationPlugin(BaseCompanionPlugin):
    """Plugin handling Notification listing, SMS/OTP interception, Missed calls, and WhatsApp messages."""

    def __init__(self):
        self.received_notifications: List[Dict[str, Any]] = []
        self.intercepted_otps: List[Dict[str, Any]] = []
        self.missed_calls: List[Dict[str, Any]] = []
        self.whatsapp_messages: List[Dict[str, Any]] = []

    @property
    def plugin_name(self) -> str:
        return "system.notifications"

    @property
    def supported_actions(self) -> List[str]:
        return ["notification.list_active"]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "device_id": device_id,
            "status": "query_dispatched"
        }

    async def on_event(self, event: EventMessage):
        """Processes notification event bus messages."""
        evt_type = event.event
        payload = event.payload

        if evt_type == "notification.received":
            self.received_notifications.append(payload)
            logger.info(f"Notification received: {payload.get('title')} from {payload.get('package_name')}")

        elif evt_type == "otp.detected":
            self.intercepted_otps.append(payload)
            logger.warning(f"OTP DETECTED: {payload.get('otp_code')} from app {payload.get('source_app')}")

        elif evt_type == "call.missed":
            self.missed_calls.append(payload)
            logger.warning(f"MISSED CALL: {payload.get('title')} - {payload.get('text')}")

        elif evt_type == "whatsapp.received":
            self.whatsapp_messages.append(payload)
            logger.info(f"WHATSAPP MESSAGE: {payload.get('title')} -> {payload.get('text')}")
