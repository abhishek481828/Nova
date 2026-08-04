"""Unit tests for Step 3: Hardware Control Feature Plugins."""

import pytest
import asyncio

from nova.companion.plugins.plugin_registry import PluginRegistry
from nova.companion.plugins.flashlight_plugin import FlashlightPlugin
from nova.companion.plugins.volume_plugin import VolumePlugin
from nova.companion.plugins.vibration_plugin import VibrationPlugin
from nova.companion.plugins.ringtone_plugin import RingtonePlugin
from nova.companion.plugins.clipboard_plugin import ClipboardPlugin
from nova.companion.manager import CompanionManager
from nova.companion.gateway.websocket_server import connection_manager
from nova.companion.protocol.schemas import ResponseMessage, CommandStatus


def test_step3_plugins_registration():
    registry = PluginRegistry()
    registry.register_plugin(FlashlightPlugin())
    registry.register_plugin(VolumePlugin())
    registry.register_plugin(VibrationPlugin())
    registry.register_plugin(RingtonePlugin())
    registry.register_plugin(ClipboardPlugin())

    # Flashlight
    assert registry.get_plugin_for_action("flashlight.on") is not None
    assert registry.get_plugin_for_action("flashlight.off") is not None
    assert registry.get_plugin_for_action("flashlight.toggle") is not None

    # Volume
    assert registry.get_plugin_for_action("volume.set") is not None
    assert registry.get_plugin_for_action("volume.get") is not None

    # Vibration
    assert registry.get_plugin_for_action("vibration.vibrate") is not None

    # Ringtone
    assert registry.get_plugin_for_action("ringtone.play") is not None
    assert registry.get_plugin_for_action("ringtone.stop") is not None

    # Clipboard
    assert registry.get_plugin_for_action("clipboard.get") is not None
    assert registry.get_plugin_for_action("clipboard.set") is not None


@pytest.mark.asyncio
async def test_step3_plugin_executions():
    fl = FlashlightPlugin()
    res_fl = await fl.execute("dev-1", "flashlight.on", {})
    assert res_fl["state"] == "on"

    vol = VolumePlugin()
    res_vol = await vol.execute("dev-1", "volume.set", {"level": 80})
    assert res_vol["volume_level"] == 80

    vib = VibrationPlugin()
    res_vib = await vib.execute("dev-1", "vibration.vibrate", {"duration_ms": 1000})
    assert res_vib["duration_ms"] == 1000

    rt = RingtonePlugin()
    res_rt = await rt.execute("dev-1", "ringtone.play", {})
    assert res_rt["status"] == "playing"

    cb = ClipboardPlugin()
    res_cb = await cb.execute("dev-1", "clipboard.set", {"text": "Nova v2.0 Rulez"})
    assert res_cb["text"] == "Nova v2.0 Rulez"


@pytest.mark.asyncio
async def test_companion_manager_routing_with_mock_ws():
    mgr = CompanionManager()
    
    # Register mock websocket connection
    class MockWebSocket:
        async def send_text(self, text: str):
            pass

    mock_ws = MockWebSocket()
    await connection_manager.connect("phone-99", mock_ws)
    mgr.device_manager.register_or_update_device("phone-99", "Galaxy Phone", "android", ["flashlight.on"])

    # Simulate async response handling
    async def mock_respond():
        await asyncio.sleep(0.05)
        for cmd_id in list(connection_manager._pending_commands.keys()):
            resp = ResponseMessage(
                command_id=cmd_id,
                action="flashlight.on",
                status=CommandStatus.SUCCESS,
                data={"state": "on"}
            )
            connection_manager.handle_response_message(resp)

    task = asyncio.create_task(mock_respond())
    result = await mgr.execute_phone_action("flashlight.on", {}, device_id="phone-99")
    await task

    assert result["status"] == "success"
    assert result["data"]["state"] == "on"
    connection_manager.disconnect("phone-99")
