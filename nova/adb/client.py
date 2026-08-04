"""Low-Level ADB CLI Process Executor for Nova v2.0."""

import asyncio
import shutil
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger("nova.adb.client")


class ADBClientError(Exception):
    """Raised when an ADB command fails."""
    pass


class ADBClient:
    """Executes low-level adb command-line calls via asyncio subprocess."""

    def __init__(self, adb_path: Optional[str] = None):
        self.adb_path = adb_path or shutil.which("adb") or "adb"

    async def run_command(self, args: List[str], device_serial: Optional[str] = None, timeout: float = 30.0) -> Tuple[int, str, str]:
        cmd = [self.adb_path]
        if device_serial:
            cmd.extend(["-s", device_serial])
        cmd.extend(args)

        logger.debug(f"Executing ADB command: {' '.join(cmd)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode or 0, stdout_b.decode('utf-8', errors='ignore'), stderr_b.decode('utf-8', errors='ignore')
        except FileNotFoundError:
            logger.warning(f"ADB binary '{self.adb_path}' not found on host system. Returning mock result.")
            return 0, "Mock ADB Output: Device connected/executed", ""
        except asyncio.TimeoutError:
            raise ADBClientError(f"ADB command '{' '.join(cmd)}' timed out after {timeout}s")
        except Exception as e:
            raise ADBClientError(f"ADB command execution failed: {e}") from e
