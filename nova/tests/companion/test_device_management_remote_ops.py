"""Phase I Automated Test Suite: Device Management & Remote Operations System."""

import os
import json
import pytest
import tempfile
from unittest.mock import patch, MagicMock

from nova.actions.device_management import (
    DeviceInfoAction,
    DeviceHealthAction,
    DeviceStorageAction,
    DeviceMemoryAction,
    DeviceCpuAction,
    DeviceNetworkAction,
    DeviceBatteryAction,
    FileListAction,
    FileUploadAction,
    FileDownloadAction,
    FileDeleteAction,
    FileRenameAction,
    FileMoveAction,
    FileCopyAction,
    DeviceLogsAction,
    DevicePerformanceAction,
    DeviceProcessesAction,
    DeviceCrashReportAction,
    DeviceBackupAction,
    DeviceRestoreAction,
    DeviceRestartCompanionAction,
    DeviceClearCacheAction,
    DeviceClearLogsAction,
    DeviceUpdateStatusAction,
)
from nova.actions.adb_remote import (
    AdbDiscoverAction,
    AdbPairAction,
    AdbConnectAction,
    AdbDisconnectAction,
    AdbStatusAction,
    AdbDevicesAction,
    AdbShellAction,
    AdbInstallApkAction,
    AdbUninstallApkAction,
    AdbPushAction,
    AdbPullAction,
    AdbScreenshotAction,
    AdbLogcatAction,
    AdbRebootAction,
)
from nova.companion.security.adb_guard import global_adb_guard
from nova.companion.dashboard import RealtimeDashboardManager, global_monitoring_dashboard


def test_device_info_and_health_actions():
    info_action = DeviceInfoAction()
    health_action = DeviceHealthAction()
    
    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {
            "manufacturer": "Samsung",
            "model": "Galaxy S24",
            "android_version": "14",
            "sdk_int": 34,
            "uptime_hours": 12.5
        }
    }):
        res1 = info_action.execute({})
        assert "Galaxy S24" in res1
        assert "Android 14" in res1

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {"status": "EXCELLENT", "health_score": 95}
    }):
        res2 = health_action.execute({})
        assert "EXCELLENT" in res2
        assert "95" in res2


def test_device_storage_memory_cpu_network_battery_actions():
    stor_action = DeviceStorageAction()
    mem_action = DeviceMemoryAction()
    cpu_action = DeviceCpuAction()
    net_action = DeviceNetworkAction()
    batt_action = DeviceBatteryAction()

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {"free_gb": 45.0, "total_gb": 128.0, "free_percent": 35.1}
    }):
        assert "45.00 GB" in stor_action.execute({})

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {"available_mb": 3500.0, "total_mb": 8000.0, "available_percent": 43.75}
    }):
        assert "3500.0 MB" in mem_action.execute({})

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {"cores": 8, "architecture": "aarch64", "max_freq_khz": 2800000}
    }):
        assert "8 cores" in cpu_action.execute({})

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {"transport": "WIFI", "is_connected": True, "has_internet": True}
    }):
        assert "WIFI" in net_action.execute({})

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {"level": 85, "is_charging": False, "plug_type": "UNPLUGGED", "temperature_celsius": 32.5}
    }):
        assert "85%" in batt_action.execute({})


def test_file_manager_actions():
    list_action = FileListAction()
    upload_action = FileUploadAction()
    download_action = FileDownloadAction()
    delete_action = FileDeleteAction()
    rename_action = FileRenameAction()
    move_action = FileMoveAction()
    copy_action = FileCopyAction()

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "files": [{"name": "test.txt", "size": 1024, "is_dir": False}]
    }):
        res1 = list_action.execute({"path": "/sdcard"})
        assert "test.txt" in res1

    with tempfile.NamedTemporaryFile("w+", delete=False) as tmp_src:
        tmp_src.write("Hello Phase I")
        tmp_src_path = tmp_src.name

    try:
        with patch("nova.actions.device_management.send_companion_command", return_value={"status": "success", "bytes_written": 13}):
            res2 = upload_action.execute({"local_path": tmp_src_path, "remote_path": "/sdcard/hello.txt"})
            assert "Successfully uploaded" in res2
    finally:
        if os.path.exists(tmp_src_path):
            os.remove(tmp_src_path)

    with patch("nova.actions.device_management.send_companion_command", return_value={"status": "success"}):
        assert "Successfully deleted" in delete_action.execute({"path": "/sdcard/hello.txt"})
        assert "Successfully renamed" in rename_action.execute({"path": "/sdcard/a.txt", "new_name": "b.txt"})
        assert "Successfully moved" in move_action.execute({"source": "/sdcard/a.txt", "destination": "/sdcard/b.txt"})
        assert "Successfully copied" in copy_action.execute({"source": "/sdcard/a.txt", "destination": "/sdcard/b.txt"})


def test_device_diagnostics_and_maintenance():
    logs_action = DeviceLogsAction()
    perf_action = DevicePerformanceAction()
    procs_action = DeviceProcessesAction()
    crash_action = DeviceCrashReportAction()
    backup_action = DeviceBackupAction()
    restore_action = DeviceRestoreAction()
    clear_cache_action = DeviceClearCacheAction()

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {"logs": ["Log line 1", "Log line 2"]}
    }):
        assert "Logcat Output" in logs_action.execute({"lines": 10})

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {"heap_used_mb": 25.0, "heap_total_mb": 100.0, "active_threads": 12}
    }):
        assert "Performance Metrics" in perf_action.execute({})

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {"processes": [{"pid": 1234, "process_name": "com.nova.companion"}]}
    }):
        assert "1234" in procs_action.execute({})

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {"crash_logs": []}
    }):
        assert "No recent crash reports" in crash_action.execute({})

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "data": {"version": "2.0", "created_at": 100000}
    }):
        assert "created successfully" in backup_action.execute({})
        assert "restored successfully" in restore_action.execute({})

    with patch("nova.actions.device_management.send_companion_command", return_value={
        "status": "success",
        "freed_bytes": 50000
    }):
        assert "Successfully cleared app cache" in clear_cache_action.execute({})


def test_adb_security_guard():
    safe, msg = global_adb_guard.is_safe_command("ls -la /sdcard")
    assert safe is True
    assert msg == "OK"

    unsafe1, reason1 = global_adb_guard.is_safe_command("rm -rf /")
    assert unsafe1 is False
    assert "rejected" in reason1

    unsafe2, reason2 = global_adb_guard.is_safe_command("mkfs.ext4 /dev/block/bootdevice")
    assert unsafe2 is False

    sanitized = global_adb_guard.sanitize_argument("echo hello; rm -rf /")
    assert ";" not in sanitized


def test_adb_remote_actions():
    shell_action = AdbShellAction()
    discover_action = AdbDiscoverAction()
    connect_action = AdbConnectAction()
    devices_action = AdbDevicesAction()

    # Test dangerous shell rejection
    res_rejected = shell_action.execute({"command": "rm -rf /"})
    assert "rejected" in res_rejected

    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(stdout="device123\tdevice", stderr="", returncode=0)
        res_devices = devices_action.execute({})
        assert "device123" in res_devices

        mock_sub.return_value = MagicMock(stdout="connected to 192.168.1.50:5555", stderr="", returncode=0)
        res_conn = connect_action.execute({"ip_port": "192.168.1.50:5555"})
        assert "connected to" in res_conn


def test_realtime_dashboard_manager_and_events():
    dashboard = RealtimeDashboardManager()
    dashboard.register_device_connected("dev_100", {"name": "Test Device"})
    assert len(dashboard.connected_devices) == 1

    summary = dashboard.get_dashboard_summary()
    assert summary["connected_devices_count"] == 1
    assert "dev_100" in summary["connected_devices"]

    # Test update device state with warnings triggering EventBus events
    summary2 = dashboard.update_device_state("dev_100", {
        "battery": {"level": 10},  # <15 triggers Battery Warning
        "storage": {"used_percent": 95.0},  # >90 triggers Storage Warning
        "performance": {"active_threads": 200}  # >150 triggers Performance Warning
    })
    assert summary2["connected_devices_count"] == 1

    dashboard.set_adb_status(True)
    assert dashboard.adb_connected is True

    dashboard.register_device_disconnected("dev_100")
    assert len(dashboard.connected_devices) == 0
