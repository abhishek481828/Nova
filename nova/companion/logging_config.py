"""Structured Production Multi-Channel Logging Configuration for Nova v2.0."""

import os
import sys
import logging
from typing import Dict, Optional

LOG_DIR = os.path.expanduser("logs")

LOG_FILES = {
    "backend": "backend.log",
    "android": "android.log",
    "network": "network.log",
    "security": "security.log",
    "adb": "adb.log",
    "performance": "performance.log"
}


def setup_structured_logging(log_file: Optional[str] = None, base_dir: str = LOG_DIR, log_level: int = logging.INFO) -> logging.Logger:
    """Sets up multi-channel structured production loggers with backward compatibility."""
    if log_file is not None:
        target_dir = os.path.dirname(os.path.abspath(log_file))
    else:
        target_dir = os.path.abspath(base_dir)

    os.makedirs(target_dir, exist_ok=True)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    root_logger = logging.getLogger("nova.companion")
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Attach file handlers for each subsystem channel
    for channel, filename in LOG_FILES.items():
        filepath = log_file if (channel == "backend" and log_file) else os.path.join(target_dir, filename)
        file_handler = logging.FileHandler(filepath, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        
        # Attach to corresponding sub-logger or root
        sub_logger = logging.getLogger(f"nova.companion.{channel}")
        sub_logger.setLevel(log_level)
        sub_logger.addHandler(file_handler)
        
        if channel == "backend":
            root_logger.addHandler(file_handler)

    root_logger.info(f"Production multi-channel logging initialized in '{target_dir}'.")
    return root_logger
