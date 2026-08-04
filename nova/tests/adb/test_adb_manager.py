"""Unit tests for Step 9: ADB Management Subsystem & ADBPlugin."""

import pytest
import asyncio
from nova.adb.client import ADBClient
from nova.adb.manager import ADBManager
from nova.companion.plugins.adb_plugin import ADBPlugin
from nova.companion.plugins.plugin_registry import PluginRegistry


@pytest.mark.asyncio
async def test_adb_client_mock_execution():
    client = ADBClient(adb_path="mock_adb_bin")
    code, stdout, stderr = await client.run_command(["version"])
    assert code == 0
    assert "Mock ADB Output" in stdout


@pytest.mark.asyncio
async def test_adb_manager_operations():
    client = ADBClient(adb_path="mock_adb_bin")
    mgr = ADBManager(client=client)

    # 1. Device Discovery
    devices = await mgr.discover_devices()
    assert isinstance(devices, list)

    # 2. Wireless ADB
    res_conn = await mgr.connect_wireless("192.168.1.105", 5555)
    assert res_conn["status"] == "connected"

    # 3. Wake Device
    res_wake = await mgr.wake_device("phone-001")
    assert res_wake["status"] == "success"

    # 4. Install / Uninstall APK
    res_install = await mgr.install_apk("MockApp.apk", "phone-001")
    assert res_install["status"] == "installed"

    res_uninstall = await mgr.uninstall_apk("com.nova.companion", "phone-001")
    assert res_uninstall["status"] == "uninstalled"

    # 5. File Push / Pull
    res_push = await mgr.push_file("/tmp/local.txt", "/sdcard/remote.txt")
    assert res_push["status"] == "pushed"

    res_pull = await mgr.pull_file("/sdcard/remote.txt", "/tmp/local.txt")
    assert res_pull["status"] == "pulled"

    # 6. Capture Logcat
    logcat = await mgr.capture_logcat(lines=50)
    assert isinstance(logcat, str)

    # 7. Shell Command Execution
    res_shell = await mgr.shell_command("getprop ro.build.version.release")
    assert res_shell["exit_code"] == 0


@pytest.mark.asyncio
async def test_adb_plugin_registration_and_execution():
    registry = PluginRegistry()
    plugin = ADBPlugin()
    registry.register_plugin(plugin)

    assert registry.get_plugin_for_action("adb.discover_devices") == plugin
    assert registry.get_plugin_for_action("adb.install_apk") == plugin
    assert registry.get_plugin_for_action("adb.shell") == plugin

    res = await plugin.execute("dev-1", "adb.shell", {"command": "echo Hello Nova ADB"})
    assert res["action"] == "adb.shell"
    assert "result" in res
