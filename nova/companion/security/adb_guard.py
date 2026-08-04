"""Phase I: ADB Guard & Command Security Validator."""

import re
import time
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger("nova.companion.security.adb_guard")

DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"mkfs",
    r"dd\s+if=",
    r"format\s+",
    r"reboot\s+recovery",
    r"fastboot",
    r">: /dev/block",
    r"chmod\s+777\s+/",
]


class AdbGuard:
    """Security validator and sanitizer for remote ADB operations."""

    @staticmethod
    def is_safe_command(cmd: str) -> Tuple[bool, str]:
        cmd_lower = cmd.lower().strip()
        
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, cmd_lower):
                logger.warning(f"Blocked dangerous ADB command pattern: '{pattern}' in '{cmd}'")
                return False, f"Command rejected: dangerous operation detected ('{pattern}')"
        
        return True, "OK"

    @staticmethod
    def sanitize_argument(arg: str) -> str:
        # Removes dangerous shell metacharacters for sub-process calls
        cleaned = re.sub(r"[;&|`$]", "", arg)
        return cleaned.strip()

    @staticmethod
    def log_operation(operation_name: str, target: str, status: str, execution_time_ms: float):
        logger.info(f"AUDIT LOG | Op: '{operation_name}' | Target: '{target}' | Status: '{status}' | Duration: {execution_time_ms:.2f}ms")


global_adb_guard = AdbGuard()
