import logging
import sys
import os
from nova.config import LOG_FILE_PATH

# Ensure parent directory of log file exists
LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Configure logger
logger = logging.getLogger("nova")

debug_mode = (
    os.environ.get("NOVA_DEBUG", "false").lower() == "true" or
    os.environ.get("NOVA_DEBUG", "false").lower() == "true"
)

if debug_mode:
    logger.setLevel(logging.DEBUG)
    file_level = logging.DEBUG
else:
    logger.setLevel(logging.INFO)
    file_level = logging.INFO

# File Handler
file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
file_handler.setLevel(file_level)
file_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

class ConsoleFormatter(logging.Formatter):
    def format(self, record):
        orig_exc_info = record.exc_info
        orig_exc_text = record.exc_text
        record.exc_info = None
        record.exc_text = None
        try:
            return super().format(record)
        finally:
            record.exc_info = orig_exc_info
            record.exc_text = orig_exc_text

# Console Handler (Only show INFO/WARNING/ERROR to console)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.WARNING)
console_formatter = ConsoleFormatter("[%(levelname)s] %(message)s")
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Dashboard Log Handler (Sends daemon logs to Dashboard WebSocket)
class DashboardLogHandler(logging.Handler):
    def emit(self, record):
        # Prevent recursion by ignoring async/network loop loggers
        ignored_loggers = ("aiohttp", "websockets", "asyncio", "urllib3")
        if any(ignored in record.name for ignored in ignored_loggers):
            return
        try:
            formatted_msg = self.format(record)
            from nova.dashboard.event_bus import emit
            emit("log_message", module="logger", status="success", metadata={
                "message": formatted_msg,
                "level": record.levelname,
                "logger": record.name
            })
        except Exception:
            pass

dashboard_handler = DashboardLogHandler()
dashboard_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
dashboard_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
dashboard_handler.setFormatter(dashboard_formatter)
logger.addHandler(dashboard_handler)

def log_request(user_input: str) -> None:
    logger.info(f"User Request: {user_input!r}")

def log_command(command: str, exit_code: int = 0, output: str = "") -> None:
    logger.info(f"Executed command: {command!r} [Exit: {exit_code}]")
    if output:
        logger.debug(f"Command Output: {output.strip()}")

def log_error(message: str, exception: Exception = None) -> None:
    if exception:
        logger.error(f"{message}: {str(exception)}", exc_info=True)
    else:
        logger.error(message)
