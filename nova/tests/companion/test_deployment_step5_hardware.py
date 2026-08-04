"""Unit tests for Deployment Step 5: Hardware Control System."""

import pytest
import asyncio
from nova.companion.plugins.flashlight_plugin import FlashlightPlugin
from nova.companion.plugins.volume_plugin import VolumePlugin
from nova.companion.plugins.vibration_plugin import VibrationPlugin
from nova.companion.plugins.ringtone_plugin import RingtonePlugin
from nova.companion.plugins.clipboard_plugin import ClipboardPlugin
from nova.companion.plugins.plugin_registry import PluginRegistry
from nova.companion.manager import CompanionManager


def test_hardware_plugin_registration():
    registry = PluginRegistry()
    flash = FlashlightPlugin()
    vol = VolumePlugin()
    vib = VibrationPlugin()
    ring = RingtonePlugin()
    clip = ClipboardPlugin()

    registry.register_plugin(flash)
    registry.register_plugin(vol)
    registry.register_plugin(vib)
    registry.register_plugin(ring)
    registry.register_plugin(clip)

    # Flashlight
    assert registry.get_plugin_for_action("flashlight.on") == flash
    assert registry.get_plugin_for_action("flashlight.off") == flash
    assert registry.get_plugin_for_action("flashlight.toggle") == flash
    assert registry.get_plugin_for_action("flashlight.status") == flash

    # Volume
    assert registry.get_plugin_for_action("volume.get") == vol
    assert registry.get_plugin_for_action("volume.set") == vol
    assert registry.get_plugin_for_action("volume.increase") == vol
    assert registry.get_plugin_for_action("volume.decrease") == vol
    assert registry.get_plugin_for_action("volume.mute") == vol

    # Vibration
    assert registry.get_plugin_for_action("vibration.short") == vib
    assert registry.get_plugin_for_action("vibration.custom") == vib

    # Ringtone
    assert registry.get_plugin_for_action("ringtone.play") == ring
    assert registry.get_plugin_for_action("ringtone.stop") == ring

    # Clipboard
    assert registry.get_plugin_for_action("clipboard.get") == clip
    assert registry.get_plugin_for_action("clipboard.set") == clip
    assert registry.get_plugin_for_action("clipboard.clear") == clip


@pytest.mark.asyncio
async def test_flashlight_execution():
    plugin = FlashlightPlugin()

    res_on = await plugin.execute("dev-a13", "flashlight.on", {})
    assert res_on["action"] == "flashlight.on"

    res_status = await plugin.execute("dev-a13", "flashlight.status", {})
    assert res_status["action"] == "flashlight.status"


@pytest.mark.asyncio
async def test_volume_execution():
    plugin = VolumePlugin()

    res_set = await plugin.execute("dev-a13", "volume.set", {"stream": "media", "percent": 70})
    assert res_set["action"] == "volume.set"
    assert res_set["stream"] == "media"
    assert res_set["percent"] == 70

    res_inc = await plugin.execute("dev-a13", "volume.increase", {"stream": "ring", "step": 2})
    assert res_inc["action"] == "volume.increase"


@pytest.mark.asyncio
async def test_vibration_execution():
    plugin = VibrationPlugin()

    res_short = await plugin.execute("dev-a13", "vibration.short", {})
    assert res_short["action"] == "vibration.short"

    res_custom = await plugin.execute("dev-a13", "vibration.custom", {"duration_ms": 600})
    assert res_custom["action"] == "vibration.custom"
    assert res_custom["duration_ms"] == 600


@pytest.mark.asyncio
async def test_ringtone_execution():
    plugin = RingtonePlugin()

    res_play = await plugin.execute("dev-a13", "ringtone.play", {})
    assert res_play["action"] == "ringtone.play"

    res_stop = await plugin.execute("dev-a13", "ringtone.stop", {})
    assert res_stop["action"] == "ringtone.stop"


@pytest.mark.asyncio
async def test_clipboard_execution():
    plugin = ClipboardPlugin()

    res_set = await plugin.execute("dev-a13", "clipboard.set", {"text": "Nova Companion Text"})
    assert res_set["text"] == "Nova Companion Text"

    res_get = await plugin.execute("dev-a13", "clipboard.get", {})
    assert res_get["text"] == "Nova Companion Text"

    res_clear = await plugin.execute("dev-a13", "clipboard.clear", {})
    assert res_clear["status"] == "cleared"


@pytest.mark.asyncio
async def test_unregistered_command_error_handling():
    mgr = CompanionManager()
    res = await mgr.execute_phone_action("invalid.unsupported_action", {}, device_id="offline-dev")

    assert res["status"] == "error"
    assert "No registered plugin" in res["error"]
