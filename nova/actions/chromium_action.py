import os
import json
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.executor import CommandExecutor
from nova.utils import print_info, print_warning
from nova.browser_manager import BrowserManager
from nova.browser_helper import run_automation

class ChromiumAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "chromium_action"

    @property
    def is_long_running(self) -> bool:
        return True

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "open").strip().lower()

        # Format URL for open operations
        if operation == "open":
            url = params.get("url", "").strip()
            if url:
                # Append .com if TLD is missing (e.g. "chatgpt")
                if "." not in url and not url.startswith(("http://", "https://")):
                    url = url + ".com"
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                params["url"] = url

        # Ensure Chromium is running with debugging enabled
        if not BrowserManager.ensure_browser():
            return f"Error: Could not launch Chromium with debugging port {BrowserManager.PORT}."

        # Locate browser_helper.py
        current_dir = Path(__file__).resolve().parent
        helper_path = current_dir.parent / "browser_helper.py"

        if not helper_path.exists():
            return f"Error: Browser automation helper script not found at {helper_path}"

        from nova.voice.config import enable_debug
        if enable_debug:
            print_info(f"Executing web automation step: {params.get('operation', 'open')}...")

        import threading
        # Playwright objects are bound to the thread they were created in.
        # If we are in a background thread (e.g. voice loop), we MUST use subprocess.
        if threading.current_thread() is not threading.main_thread():
            self.run_in_process = False

        if getattr(self, "run_in_process", True):
            try:
                result = run_automation(params)
                status = result.get("status")
                message = result.get("message", "Web step completed successfully.")
                return f"✅ {message}" if status == "success" else f"❌ {message}"
            except Exception as e:
                from nova.logger import logger
                import traceback
                logger.error(f"In-process browser automation failed, falling back to subprocess: {e}\n{traceback.format_exc()}")
                # Fall through to subprocess execution
        
        # Subprocess execution fallback
        import sys
        cmd = [sys.executable, str(helper_path), json.dumps(params)]
        exit_code, stdout, stderr = CommandExecutor.run_shell(cmd, require_confirmation=False)

        if exit_code != 0:
            return f"Error: Web automation script failed (exit {exit_code}). Stderr: {stderr.strip()}"

        try:
            result = json.loads(stdout.strip())
            status = result.get("status")
            message = result.get("message", "Web step completed successfully.")
            return f"✅ {message}" if status == "success" else f"❌ {message}"
        except json.JSONDecodeError:
            if "success" in stdout.lower() or "playing" in stdout.lower():
                return f"✅ Web step completed: {stdout.strip()[:200]}"
            return f"Error: Failed to parse automation helper response. Output: {stdout.strip()[:300]}"
