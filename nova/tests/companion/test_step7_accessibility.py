"""Unit tests for Step 7: Accessibility Engine & UI Automation."""

import pytest
import asyncio
from nova.companion.plugins.accessibility_plugins import AccessibilityPlugin
from nova.companion.plugins.system_plugins import AppLauncherPlugin
from nova.companion.plugins.plugin_registry import PluginRegistry


def test_accessibility_and_launcher_plugin_registration():
    registry = PluginRegistry()
    acc_plugin = AccessibilityPlugin()
    app_plugin = AppLauncherPlugin()
    registry.register_plugin(acc_plugin)
    registry.register_plugin(app_plugin)

    assert registry.get_plugin_for_action("accessibility.dump_tree") == acc_plugin
    assert registry.get_plugin_for_action("accessibility.click") == acc_plugin
    assert registry.get_plugin_for_action("accessibility.type") == acc_plugin
    assert registry.get_plugin_for_action("accessibility.scroll") == acc_plugin
    assert registry.get_plugin_for_action("accessibility.global_action") == acc_plugin

    assert registry.get_plugin_for_action("app.launch") == app_plugin
    assert registry.get_plugin_for_action("app.list") == app_plugin


@pytest.mark.asyncio
async def test_accessibility_plugin_executions():
    acc_plugin = AccessibilityPlugin()

    # Dump tree
    res_tree = await acc_plugin.execute("phone-a13", "accessibility.dump_tree", {})
    assert res_tree["action"] == "accessibility.dump_tree"

    # Click
    res_click = await acc_plugin.execute("phone-a13", "accessibility.click", {"text": "Login"})
    assert res_click["target"] == "Login"

    # Type
    res_type = await acc_plugin.execute("phone-a13", "accessibility.type", {"view_id": "input_user", "text": "nova_user"})
    assert res_type["target"] == "input_user"

    # Scroll
    res_scroll = await acc_plugin.execute("phone-a13", "accessibility.scroll", {"direction": "forward"})
    assert res_scroll["action"] == "accessibility.scroll"

    # Global Action
    res_global = await acc_plugin.execute("phone-a13", "accessibility.global_action", {"action_id": 1})
    assert res_global["action"] == "accessibility.global_action"


@pytest.mark.asyncio
async def test_app_launcher_plugin_executions():
    app_plugin = AppLauncherPlugin()
    res_launch = await app_plugin.execute("phone-a13", "app.launch", {"package_name": "com.whatsapp"})

    assert res_launch["action"] == "app.launch"
    assert res_launch["package_name"] == "com.whatsapp"
