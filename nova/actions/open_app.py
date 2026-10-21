import json
import os
import shutil
import difflib
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.config import APPS_JSON_PATH
from nova.core.executor import CommandExecutor
from nova.logger import log_error
from nova.utils import print_info

class OpenAppAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "open_app"

    def execute(self, params: Dict[str, Any]) -> str:
        app_name = params.get("app", "").strip().lower()
        if not app_name:
            return "Error: No application name provided in parameters."

        # Route ChatGPT requests
        if app_name in ("chatgpt", "gpt", "chat gpt"):
            from nova.actions.chatgpt import ChatGPTAction
            action = ChatGPTAction()
            if hasattr(self, "working_memory"):
                action.working_memory = self.working_memory
            return action.execute({"operation": "open"})

        # Route browser requests to BrowserManager
        if app_name in ("chromium", "chrome", "google chrome"):
            from nova.browser.manager import BrowserManager
            from nova.config import CHROMIUM_HEADLESS
            try:
                browser_running = BrowserManager.is_browser_running()
                if browser_running and BrowserManager.get_running_browser_headless_state() == CHROMIUM_HEADLESS:
                    if BrowserManager.focus_active_window():
                        return f"Successfully focused existing {app_name} window."
                else:
                    if browser_running:
                        if BrowserManager.restart_browser():
                            return f"Successfully opened new {app_name} instance."
                    else:
                        if BrowserManager.launch_browser():
                            return f"Successfully opened new {app_name} instance."
            except Exception as e:
                log_error(f"BrowserManager failed to handle {app_name}", e)

        # Load apps map
        apps_map = {}
        if APPS_JSON_PATH.exists():
            try:
                with open(APPS_JSON_PATH, "r", encoding="utf-8") as f:
                    apps_map = json.load(f)
            except Exception as e:
                log_error("Failed to parse apps.json configuration", e)

        executable = app_name
        if app_name in apps_map:
            executable = apps_map[app_name]
        else:
            matches = difflib.get_close_matches(app_name, apps_map.keys(), n=1, cutoff=0.5)
            if matches:
                executable = apps_map[matches[0]]

        # Platform-specific executable normalization
        if os.name == "nt":
            if executable in ("gnome-terminal", "terminal", "xterm"):
                executable = "wt" if shutil.which("wt") else "powershell"
            elif executable in ("nautilus", "dolphin", "thunar"):
                executable = "explorer"

        # Check if the command/binary exists before running
        binary = executable.split()[0] if executable else ""
        if binary and not shutil.which(binary):
            # On Windows, try launching directly or via 'start'
            if os.name == "nt":
                exit_code, msg = CommandExecutor.run_background(f"start {executable}", shell=True)
                if exit_code == 0:
                    return f"Successfully opened {app_name}."
            return f"Error: {app_name} (command: '{executable}') is not installed or could not be found in PATH."

        exit_code, msg = CommandExecutor.run_background(executable, shell=True)
        if exit_code == 0:
            return f"Successfully opened {app_name} (command: {executable})."
        else:
            return f"Failed to open {app_name}: {msg}"
