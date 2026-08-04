"""Phase I: Wireless ADB & ADB Operations Actions for Nova v2.0."""

import time
import subprocess
from typing import Dict, Any
from nova.actions.base import BaseAction
from nova.companion.security.adb_guard import global_adb_guard


class AdbDiscoverAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_discover"

    def execute(self, params: Dict[str, Any]) -> str:
        t0 = time.time()
        proc = subprocess.run("adb mdns check", shell=True, capture_output=True, text=True)
        dur = (time.time() - t0) * 1000.0
        global_adb_guard.log_operation("adb_discover", "network", "success", dur)
        return f"Wireless ADB mDNS Discovery:\n{proc.stdout.strip() or 'mDNS discovery active'}"


class AdbPairAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_pair"

    def execute(self, params: Dict[str, Any]) -> str:
        t0 = time.time()
        ip_port = str(params.get("ip_port", params.get("address", "")))
        code = str(params.get("code", params.get("pairing_code", "")))
        if not ip_port or not code:
            return "Failed to pair Wireless ADB: Missing ip_port or pairing_code."

        proc = subprocess.run(f"adb pair {ip_port} {code}", shell=True, capture_output=True, text=True)
        dur = (time.time() - t0) * 1000.0
        out = proc.stdout.strip() or proc.stderr.strip()
        global_adb_guard.log_operation("adb_pair", ip_port, "completed", dur)
        return f"Wireless ADB Pair ({ip_port}): {out}"


class AdbConnectAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_connect"

    def execute(self, params: Dict[str, Any]) -> str:
        t0 = time.time()
        ip_port = str(params.get("ip_port", params.get("address", "")))
        if not ip_port:
            return "Failed to connect Wireless ADB: Missing ip_port."

        proc = subprocess.run(f"adb connect {ip_port}", shell=True, capture_output=True, text=True)
        dur = (time.time() - t0) * 1000.0
        out = proc.stdout.strip()
        global_adb_guard.log_operation("adb_connect", ip_port, "completed", dur)
        return f"Wireless ADB Connect ({ip_port}): {out}"


class AdbDisconnectAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_disconnect"

    def execute(self, params: Dict[str, Any]) -> str:
        t0 = time.time()
        ip_port = str(params.get("ip_port", params.get("address", "")))
        cmd = f"adb disconnect {ip_port}" if ip_port else "adb disconnect"
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        dur = (time.time() - t0) * 1000.0
        global_adb_guard.log_operation("adb_disconnect", ip_port or "all", "completed", dur)
        return f"Wireless ADB Disconnect: {proc.stdout.strip()}"


class AdbStatusAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_status"

    def execute(self, params: Dict[str, Any]) -> str:
        proc = subprocess.run("adb devices -l", shell=True, capture_output=True, text=True)
        return f"Wireless ADB Status:\n{proc.stdout.strip()}"


class AdbDevicesAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_devices"

    def execute(self, params: Dict[str, Any]) -> str:
        proc = subprocess.run("adb devices", shell=True, capture_output=True, text=True)
        return f"Connected ADB Devices:\n{proc.stdout.strip()}"


class AdbShellAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_shell"

    def execute(self, params: Dict[str, Any]) -> str:
        t0 = time.time()
        cmd = str(params.get("command", params.get("cmd", "")))
        if not cmd:
            return "Failed to run ADB shell: Empty command."

        safe, reason = global_adb_guard.is_safe_command(cmd)
        if not safe:
            global_adb_guard.log_operation("adb_shell", cmd, "blocked", 0.0)
            return reason

        proc = subprocess.run(f"adb shell \"{cmd}\"", shell=True, capture_output=True, text=True)
        dur = (time.time() - t0) * 1000.0
        global_adb_guard.log_operation("adb_shell", cmd, "success", dur)
        return f"ADB Shell Output:\n{proc.stdout.strip() or proc.stderr.strip()}"


class AdbInstallApkAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_install_apk"

    def execute(self, params: Dict[str, Any]) -> str:
        t0 = time.time()
        apk_path = str(params.get("apk_path", params.get("path", "")))
        if not apk_path:
            return "Failed to install APK: Missing apk_path."

        proc = subprocess.run(f"adb install -r '{apk_path}'", shell=True, capture_output=True, text=True)
        dur = (time.time() - t0) * 1000.0
        out = proc.stdout.strip() or proc.stderr.strip()
        global_adb_guard.log_operation("adb_install_apk", apk_path, "success", dur)
        return f"ADB APK Install ({apk_path}): {out}"


class AdbUninstallApkAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_uninstall_apk"

    def execute(self, params: Dict[str, Any]) -> str:
        t0 = time.time()
        pkg_name = str(params.get("package_name", params.get("package", "")))
        if not pkg_name:
            return "Failed to uninstall package: Missing package_name."

        proc = subprocess.run(f"adb uninstall '{pkg_name}'", shell=True, capture_output=True, text=True)
        dur = (time.time() - t0) * 1000.0
        out = proc.stdout.strip() or proc.stderr.strip()
        global_adb_guard.log_operation("adb_uninstall_apk", pkg_name, "success", dur)
        return f"ADB Package Uninstall ({pkg_name}): {out}"


class AdbPushAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_push"

    def execute(self, params: Dict[str, Any]) -> str:
        t0 = time.time()
        src = str(params.get("source", params.get("local_path", "")))
        dst = str(params.get("destination", params.get("remote_path", "")))
        if not src or not dst:
            return "Failed to push file: Missing source or destination."

        proc = subprocess.run(f"adb push '{src}' '{dst}'", shell=True, capture_output=True, text=True)
        dur = (time.time() - t0) * 1000.0
        out = proc.stdout.strip() or proc.stderr.strip()
        global_adb_guard.log_operation("adb_push", f"{src}->{dst}", "success", dur)
        return f"ADB Push ({src} -> {dst}): {out}"


class AdbPullAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_pull"

    def execute(self, params: Dict[str, Any]) -> str:
        t0 = time.time()
        src = str(params.get("source", params.get("remote_path", "")))
        dst = str(params.get("destination", params.get("local_path", "")))
        if not src or not dst:
            return "Failed to pull file: Missing source or destination."

        proc = subprocess.run(f"adb pull '{src}' '{dst}'", shell=True, capture_output=True, text=True)
        dur = (time.time() - t0) * 1000.0
        out = proc.stdout.strip() or proc.stderr.strip()
        global_adb_guard.log_operation("adb_pull", f"{src}->{dst}", "success", dur)
        return f"ADB Pull ({src} -> {dst}): {out}"


class AdbScreenshotAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_screenshot"

    def execute(self, params: Dict[str, Any]) -> str:
        t0 = time.time()
        out_path = str(params.get("output_path", "/tmp/adb_screenshot.png"))
        proc = subprocess.run(f"adb exec-out screencap -p > '{out_path}'", shell=True, capture_output=True)
        dur = (time.time() - t0) * 1000.0
        global_adb_guard.log_operation("adb_screenshot", out_path, "success", dur)
        return f"ADB Screenshot captured to '{out_path}'."


class AdbLogcatAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_logcat"

    def execute(self, params: Dict[str, Any]) -> str:
        lines = int(params.get("lines", 50))
        proc = subprocess.run(f"adb logcat -d -t {lines}", shell=True, capture_output=True, text=True)
        return f"ADB Logcat Output:\n" + "\n".join(proc.stdout.strip().splitlines()[-20:])


class AdbRebootAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_reboot"

    def execute(self, params: Dict[str, Any]) -> str:
        mode = str(params.get("mode", "")).strip()
        cmd = f"adb reboot {mode}".strip()
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        global_adb_guard.log_operation("adb_reboot", mode or "system", "executed", 0.0)
        return f"ADB Reboot signal issued ({mode or 'system'})."
