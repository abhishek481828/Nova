"""Companion Subsystem Orchestrator for Nova v2.0."""

import logging
from typing import Any, Dict, Optional, List
from nova.companion.devices.device_manager import DeviceManager
from nova.companion.events.event_bus import EventBus
from nova.companion.plugins.plugin_registry import PluginRegistry
from nova.companion.plugins.device_info import DeviceInfoPlugin
from nova.companion.plugins.camera_plugin import CameraPlugin
from nova.companion.plugins.gallery_plugin import GalleryPlugin
from nova.companion.plugins.screen_plugin import ScreenPlugin
from nova.companion.plugins.audio_plugin import AudioPlugin
from nova.companion.plugins.adb_plugin import ADBPlugin
from nova.companion.plugins.flashlight_plugin import FlashlightPlugin
from nova.companion.plugins.volume_plugin import VolumePlugin
from nova.companion.plugins.vibration_plugin import VibrationPlugin
from nova.companion.plugins.ringtone_plugin import RingtonePlugin
from nova.companion.plugins.clipboard_plugin import ClipboardPlugin
from nova.companion.plugins.notification_plugin import NotificationPlugin
from nova.companion.plugins.hardware_plugins import LocationPlugin
from nova.companion.plugins.system_plugins import SMSPlugin, AppLauncherPlugin
from nova.companion.plugins.communication_plugins import CallPlugin, ContactsPlugin
from nova.companion.plugins.accessibility_plugins import AccessibilityPlugin
from nova.companion.gateway.websocket_server import connection_manager
from nova.companion.protocol.schemas import CommandMessage, CommandStatus

logger = logging.getLogger("nova.companion.manager")


class CompanionManager:
    """Central Orchestrator for Nova v2.0 Companion System."""

    def __init__(self):
        self.device_manager = DeviceManager()
        self.event_bus = EventBus()
        self.plugin_registry = PluginRegistry()
        self.notification_plugin = NotificationPlugin()
        self.audio_plugin = AudioPlugin()
        self.adb_plugin = ADBPlugin()
        self._register_default_plugins()
        self._subscribe_event_bus()

    def _register_default_plugins(self):
        self.plugin_registry.register_plugin(self.adb_plugin)
        self.plugin_registry.register_plugin(ScreenPlugin())
        self.plugin_registry.register_plugin(self.audio_plugin)
        self.plugin_registry.register_plugin(CameraPlugin())
        self.plugin_registry.register_plugin(GalleryPlugin())
        self.plugin_registry.register_plugin(self.notification_plugin)
        self.plugin_registry.register_plugin(DeviceInfoPlugin())
        self.plugin_registry.register_plugin(FlashlightPlugin())
        self.plugin_registry.register_plugin(VolumePlugin())
        self.plugin_registry.register_plugin(VibrationPlugin())
        self.plugin_registry.register_plugin(RingtonePlugin())
        self.plugin_registry.register_plugin(ClipboardPlugin())
        self.plugin_registry.register_plugin(LocationPlugin())
        self.plugin_registry.register_plugin(SMSPlugin())
        self.plugin_registry.register_plugin(CallPlugin())
        self.plugin_registry.register_plugin(ContactsPlugin())
        self.plugin_registry.register_plugin(AppLauncherPlugin())
        self.plugin_registry.register_plugin(AccessibilityPlugin())
        logger.info("Initialized default companion feature plugins for Step 6 Communication System.")

    def _subscribe_event_bus(self):
        self.event_bus.subscribe("notification.received", self.notification_plugin.on_event)
        self.event_bus.subscribe("otp.detected", self.notification_plugin.on_event)
        self.event_bus.subscribe("call.missed", self.notification_plugin.on_event)
        self.event_bus.subscribe("whatsapp.received", self.notification_plugin.on_event)

    async def execute_phone_action(self, action: str, payload: Dict[str, Any], device_id: Optional[str] = None) -> dict:
        """Executes a phone action on target companion device."""
        if not device_id:
            online_devices = self.device_manager.list_online_devices()
            if not online_devices:
                return {"status": "error", "error": "No companion devices currently online"}
            device_id = online_devices[0].device_id

        plugin = self.plugin_registry.get_plugin_for_action(action)
        if not plugin:
            return {"status": "error", "error": f"No registered plugin handles action '{action}'"}

        cmd = CommandMessage(
            target=device_id,
            action=action,
            payload=payload
        )

        logger.info(f"Dispatching command {action} (ID {cmd.id}) to companion device {device_id}")
        response = await connection_manager.send_command(cmd)

        if response.error and "not connected over WebSocket" in response.error:
            # Fallback HTTP call to running Gateway server instance on port 8000
            try:
                import urllib.request, json
                req_data = json.dumps({
                    "device_id": device_id,
                    "action": action,
                    "payload": payload
                }).encode("utf-8")
                req = urllib.request.Request(
                    "http://127.0.0.1:8000/api/v2/companion/command",
                    data=req_data,
                    headers={"Content-Type": "application/json"}
                )
                http_resp = urllib.request.urlopen(req, timeout=10).read()
                return json.loads(http_resp.decode())
            except Exception as e:
                logger.warning(f"HTTP Gateway proxy call failed: {e}")

        return {
            "id": response.id,
            "status": response.status.value,
            "action": response.action,
            "data": response.data,
            "error": response.error
        }
