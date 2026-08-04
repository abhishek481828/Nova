"""Phase J Automated Test Suite: Production Hardening, Release & Final Validation."""

import os
import subprocess
import pytest
from nova.companion.logging_config import setup_structured_logging, LOG_FILES
from nova.companion.security.adb_guard import global_adb_guard


def test_production_documentation_suite_exists():
    required_docs = [
        "README.md",
        "INSTALLATION.md",
        "ANDROID_SETUP.md",
        "API_REFERENCE.md",
        "ARCHITECTURE.md",
        "DEVELOPER_GUIDE.md",
        "USER_GUIDE.md",
        "TROUBLESHOOTING.md",
        "SECURITY.md",
        "CHANGELOG.md",
        "RELEASE_NOTES.md"
    ]
    for doc in required_docs:
        path = os.path.join(os.path.dirname(__file__), "../../../", doc)
        assert os.path.exists(path), f"Missing production documentation file: {doc}"
        assert os.path.getsize(path) > 50, f"Documentation file '{doc}' is empty or too short."


def test_deployment_scripts_exist_and_executable():
    required_scripts = ["install.sh", "start.sh", "update.sh", "backup.sh", "restore.sh", "release.sh"]
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    for script in required_scripts:
        path = os.path.join(base_dir, script)
        assert os.path.exists(path), f"Missing deployment script: {script}"
        assert os.access(path, os.X_OK), f"Deployment script '{script}' is not executable."

    # Test start.sh syntax check mode
    proc = subprocess.run([os.path.join(base_dir, "start.sh"), "--check"], capture_output=True, text=True)
    assert proc.returncode == 0
    assert "Start Script OK" in proc.stdout


def test_multi_channel_logging_initialization(tmp_path):
    log_dir = str(tmp_path / "logs")
    logger = setup_structured_logging(base_dir=log_dir)
    assert logger is not None
    assert os.path.exists(log_dir)

    for channel, filename in LOG_FILES.items():
        filepath = os.path.join(log_dir, filename)
        assert os.path.exists(filepath), f"Log file '{filename}' was not created for channel '{channel}'"


def test_security_audit_validation():
    # Test ADB dangerous command rejection
    safe, _ = global_adb_guard.is_safe_command("adb shell dumpsys battery")
    assert safe is True

    unsafe, reason = global_adb_guard.is_safe_command("rm -rf /")
    assert unsafe is False
    assert "dangerous" in reason.lower()

    # Test argument sanitization
    sanitized = global_adb_guard.sanitize_argument("test; rm -rf /")
    assert ";" not in sanitized
