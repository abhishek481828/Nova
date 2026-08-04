"""Security Audit Logging for Nova v2.0."""

import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("nova.companion.security.audit")
logger.setLevel(logging.INFO)


class AuditLogger:
    @staticmethod
    def log_event(
        device_id: str,
        action: str,
        status: str,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        record = {
            "timestamp": time.time(),
            "device_id": device_id,
            "action": action,
            "status": status,
            "error_message": error_message,
            "details": details or {}
        }
        if status.upper() == "ALLOWED" or status.upper() == "SUCCESS":
            logger.info(f"AUDIT SUCCESS: {record}")
        else:
            logger.warning(f"AUDIT FAILURE/DENIED: {record}")
        return record
