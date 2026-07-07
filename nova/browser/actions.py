import json
import webbrowser
import threading
import sys
from pathlib import Path
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor
from nova.utils import print_info
from nova.browser.manager import BrowserManager
from nova.browser.helper import run_automation
from nova.browser.runner import BrowserRunner

class BrowserAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "browser_action"

    def execute(self, params: Dict[str, Any]) -> str:
        url = params.get("url", "").strip()
        if not url:
            return "Error: No URL provided for browser action."

        # Add https scheme if not present
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        print_info(f"Opening URL in default browser: {url}")
        
        success = webbrowser.open(url)
        
        if success:
            return f"Successfully opened default browser to: {url}"
        else:
            return f"Webbrowser module failed to launch url: {url}"


class ChromiumAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "chromium_action"

    @property
    def is_long_running(self) -> bool:
        return True

    def execute(self, params: Dict[str, Any]) -> str:
        # Propagate working memory to BrowserManager
        if hasattr(self, "working_memory") and self.working_memory is not None:
            BrowserManager._working_memory = self.working_memory

        try:
            return self._execute_inner(params)
        finally:
            # Sync browser state to memory at end of action
            try:
                if hasattr(self, "working_memory") and self.working_memory is not None:
                    BrowserManager.trigger_memory_update()
            except Exception as e:
                pass

    def _execute_inner(self, params: Dict[str, Any]) -> str:
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

        # Locate helper.py
        current_dir = Path(__file__).resolve().parent
        helper_path = current_dir / "helper.py"

        if not helper_path.exists():
            return f"Error: Browser automation helper script not found at {helper_path}"

        from nova.voice.config import enable_debug
        if enable_debug:
            print_info(f"Executing web automation step: {params.get('operation', 'open')}...")


        try:
            result = BrowserRunner.execute(run_automation, params)
            status = result.get("status")
            message = result.get("message", "Web step completed successfully.")
            return f"✅ {message}" if status == "success" else f"❌ {message}"
        except Exception as e:
            from nova.logger import logger
            import traceback
            logger.error(f"In-process browser automation via BrowserRunner failed: {e}\n{traceback.format_exc()}")
            return f"❌ Browser automation failed: {e}"
