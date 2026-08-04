"""Unit tests for Step 8: Screen Sharing, Remote Touch & Keyboard."""

import pytest
import asyncio
from nova.companion.plugins.screen_plugin import ScreenPlugin
from nova.companion.plugins.plugin_registry import PluginRegistry


def test_screen_plugin_registration():
    registry = PluginRegistry()
    plugin = ScreenPlugin()
    registry.register_plugin(plugin)

    assert registry.get_plugin_for_action("screen.capture_screenshot") == plugin
    assert registry.get_plugin_for_action("screen.record_video") == plugin
    assert registry.get_plugin_for_action("screen.start_stream") == plugin
    assert registry.get_plugin_for_action("screen.stop_stream") == plugin
    assert registry.get_plugin_for_action("screen.tap") == plugin
    assert registry.get_plugin_for_action("screen.type") == plugin


@pytest.mark.asyncio
async def test_screen_plugin_executions():
    plugin = ScreenPlugin()

    # Screenshot
    res_shot = await plugin.execute("phone-a13", "screen.capture_screenshot", {})
    assert res_shot["action"] == "screen.capture_screenshot"

    # Start Stream
    res_stream = await plugin.execute("phone-a13", "screen.start_stream", {})
    assert res_stream["action"] == "screen.start_stream"

    # Remote Touch Tap
    res_tap = await plugin.execute("phone-a13", "screen.tap", {"x": 540, "y": 1200})
    assert res_tap["coordinates"]["x"] == 540
    assert res_tap["coordinates"]["y"] == 1200

    # Remote Keyboard Input
    res_type = await plugin.execute("phone-a13", "screen.type", {"text": "Hello Nova Screen Stream"})
    assert res_type["text"] == "Hello Nova Screen Stream"
