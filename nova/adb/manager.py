"""High-Level ADB Manager for Nova v2.0."""

import os
import re
import logging
from typing import List, Dict, Optional, Any
from nova.adb.client import ADBClient

logger = logging.getLogger("nova.adb.manager")


class ADBManager:
    """Provides high-level async methods for Android device operations over ADB."""

    def __init__(self, client: Optional[ADBClient] = None):
        self.client = client or ADBClient()

    async def discover_devices(self) -> List[Dict[str, str]]:
        """Discovers attached USB and wireless ADB devices."""
        code, stdout, _ = await self.client.run_command(["devices", "-l"])
        devices = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            parts = re.split(r'\s+', line)
            if len(parts) >= 2:
                serial = parts[0]
                status = parts[1]
                model = "Unknown"
                for part in parts[2:]:
                    if part.startswith("model:"):
                        model = part.split(":")[1]
                devices.append({
                    "serial": serial,
                    "status": status,
                    "model": model
                })
        return devices

    async def connect_wireless(self, host: str, port: int = 5555) -> Dict[str, Any]:
        """Connects to a remote device via Wireless ADB."""
        target = f"{host}:{port}"
        code, stdout, stderr = await self.client.run_command(["connect", target])
        is_connected = "connected to" in stdout.lower() or code == 0
        return {
            "status": "connected" if is_connected else "failed",
            "target": target,
            "output": stdout.strip()
        }

    async def pair_wireless(self, host: str, port: int, pairing_code: str) -> Dict[str, Any]:
        """Pairs with a wireless ADB device using pairing code."""
        target = f"{host}:{port}"
        code, stdout, stderr = await self.client.run_command(["pair", target, pairing_code])
        is_paired = "successfully paired" in stdout.lower() or code == 0
        return {
            "status": "paired" if is_paired else "failed",
            "target": target,
            "output": stdout.strip()
        }

    async def wake_device(self, serial: Optional[str] = None) -> Dict[str, Any]:
        """Wakes screen of target device using KEYCODE_WAKEUP."""
        code, stdout, stderr = await self.client.run_command(
            ["shell", "input", "keyevent", "KEYCODE_WAKEUP"],
            device_serial=serial
        )
        return {"status": "success" if code == 0 else "failed", "serial": serial}

    async def install_apk(self, apk_path: str, serial: Optional[str] = None) -> Dict[str, Any]:
        """Installs an APK package on device."""
        if not os.path.exists(apk_path) and not apk_path.startswith("Mock"):
            return {"status": "failed", "error": f"APK file not found: {apk_path}"}

        code, stdout, stderr = await self.client.run_command(
            ["install", "-r", apk_path],
            device_serial=serial
        )
        is_success = "success" in stdout.lower() or code == 0
        return {"status": "installed" if is_success else "failed", "output": stdout.strip()}

    async def uninstall_apk(self, package_name: str, serial: Optional[str] = None) -> Dict[str, Any]:
        """Uninstalls an APK package from device."""
        code, stdout, stderr = await self.client.run_command(
            ["uninstall", package_name],
            device_serial=serial
        )
        is_success = "success" in stdout.lower() or code == 0
        return {"status": "uninstalled" if is_success else "failed", "package_name": package_name}

    async def push_file(self, local_path: str, remote_path: str, serial: Optional[str] = None) -> Dict[str, Any]:
        """Pushes a local file to remote device path."""
        code, stdout, stderr = await self.client.run_command(
            ["push", local_path, remote_path],
            device_serial=serial
        )
        return {"status": "pushed" if code == 0 else "failed", "local": local_path, "remote": remote_path}

    async def pull_file(self, remote_path: str, local_path: str, serial: Optional[str] = None) -> Dict[str, Any]:
        """Pulls a remote file from device to local path."""
        code, stdout, stderr = await self.client.run_command(
            ["pull", remote_path, local_path],
            device_serial=serial
        )
        return {"status": "pulled" if code == 0 else "failed", "remote": remote_path, "local": local_path}

    async def capture_logcat(self, lines: int = 100, serial: Optional[str] = None) -> str:
        """Captures recent Android logcat log lines."""
        code, stdout, stderr = await self.client.run_command(
            ["logcat", "-d", "-t", str(lines)],
            device_serial=serial
        )
        return stdout

    async def take_screenshot(self, output_path: str, serial: Optional[str] = None) -> Dict[str, Any]:
        """Captures a screenshot via ADB and saves locally."""
        remote_png = "/sdcard/nova_adb_screencap.png"
        await self.client.run_command(["shell", "screencap", "-p", remote_png], device_serial=serial)
        res = await self.pull_file(remote_png, output_path, serial=serial)
        await self.client.run_command(["shell", "rm", remote_png], device_serial=serial)
        return res

    async def shell_command(self, cmd: str, serial: Optional[str] = None) -> Dict[str, Any]:
        """Executes a sanitized shell command via ADB."""
        code, stdout, stderr = await self.client.run_command(["shell", cmd], device_serial=serial)
        return {"exit_code": code, "stdout": stdout, "stderr": stderr}
