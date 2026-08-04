"""ADB Management Companion Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin
from nova.adb.manager import ADBManager


class ADBPlugin(BaseCompanionPlugin):
    """Plugin providing ADB device operations (discovery, wireless pairing, wake, APK install, push/pull, logcat, shell)."""

    def __init__(self):
        self.adb_manager = ADBManager()

    @property
    def plugin_name(self) -> str:
        return "system.adb"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "adb.discover_devices",
            "adb.connect_wireless",
            "adb.wake_device",
            "adb.install_apk",
            "adb.uninstall_apk",
            "adb.push_file",
            "adb.pull_file",
            "adb.capture_logcat",
            "adb.take_screenshot",
            "adb.shell"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        serial = payload.get("serial") or device_id

        if action == "adb.discover_devices":
            devices = await self.adb_manager.discover_devices()
            return {"action": action, "devices": devices}
        elif action == "adb.connect_wireless":
            host = payload.get("host", "127.0.0.1")
            port = payload.get("port", 5555)
            res = await self.adb_manager.connect_wireless(host, port)
            return {"action": action, "result": res}
        elif action == "adb.wake_device":
            res = await self.adb_manager.wake_device(serial)
            return {"action": action, "result": res}
        elif action == "adb.install_apk":
            apk_path = payload.get("apk_path", "")
            res = await self.adb_manager.install_apk(apk_path, serial)
            return {"action": action, "result": res}
        elif action == "adb.uninstall_apk":
            pkg = payload.get("package_name", "")
            res = await self.adb_manager.uninstall_apk(pkg, serial)
            return {"action": action, "result": res}
        elif action == "adb.push_file":
            local = payload.get("local_path", "")
            remote = payload.get("remote_path", "")
            res = await self.adb_manager.push_file(local, remote, serial)
            return {"action": action, "result": res}
        elif action == "adb.pull_file":
            remote = payload.get("remote_path", "")
            local = payload.get("local_path", "")
            res = await self.adb_manager.pull_file(remote, local, serial)
            return {"action": action, "result": res}
        elif action == "adb.capture_logcat":
            lines = payload.get("lines", 100)
            logcat = await self.adb_manager.capture_logcat(lines, serial)
            return {"action": action, "lines_returned": len(logcat.splitlines()), "logcat": logcat}
        elif action == "adb.take_screenshot":
            out_path = payload.get("output_path", "/tmp/adb_screenshot.png")
            res = await self.adb_manager.take_screenshot(out_path, serial)
            return {"action": action, "result": res}
        elif action == "adb.shell":
            cmd = payload.get("command", "getprop ro.build.version.release")
            res = await self.adb_manager.shell_command(cmd, serial)
            return {"action": action, "result": res}

        return {"action": action, "device_id": device_id, "status": "dispatched"}
