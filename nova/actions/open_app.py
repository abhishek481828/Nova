import json
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.config import APPS_JSON_PATH
from nova.executor import CommandExecutor
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

        # Route mirroring requests to self-healing mirroring handler
        if app_name in ("phone", "mirror", "connect"):
            from nova.actions.adb import start_mirroring
            return start_mirroring()

        # Route Cloudflare Warp connection requests
        if app_name in ("warp", "warp vpn", "cloudflare warp", "cloudflare-warp"):
            import subprocess
            print_info("Proactive Decision: Connecting Cloudflare Warp VPN...")
            res = subprocess.run(["warp-cli", "connect"], capture_output=True, text=True)
            output = res.stdout.strip() + "\n" + res.stderr.strip()
            if res.returncode == 0 or "success" in output.lower():
                return "✅ Successfully connected to Cloudflare Warp VPN!"
            else:
                return f"❌ Failed to connect Warp VPN: {output.strip()}"

        # Load apps map
        apps_map = {}
        if APPS_JSON_PATH.exists():
            try:
                with open(APPS_JSON_PATH, "r", encoding="utf-8") as f:
                    apps_map = json.load(f)
            except Exception as e:
                log_error("Failed to parse apps.json configuration", e)
        
        # Determine executable command
        # If the key exists, run the command. If not, check for close typos, otherwise run directly.
        executable = app_name
        if app_name in apps_map:
            executable = apps_map[app_name]
        else:
            import difflib
            matches = difflib.get_close_matches(app_name, apps_map.keys(), n=1, cutoff=0.5)
            if matches:
                closest_match = matches[0]
                executable = apps_map[closest_match]
                print_info(f"Correcting typo '{app_name}' to '{closest_match}'...")
                app_name = closest_match
        
        if executable in ("chromium", "google-chrome-stable", "chrome") or app_name in ("chromium", "chrome", "google-chrome-stable"):
            from nova.browser_manager import BrowserManager
            from nova.config import CHROMIUM_HEADLESS
            browser_running = BrowserManager.is_browser_running()
            if browser_running and BrowserManager.get_running_browser_headless_state() == CHROMIUM_HEADLESS:
                if BrowserManager.focus_active_window():
                    return f"Successfully focused existing {app_name} window."
                else:
                    return f"Failed to focus existing {app_name} window."
            else:
                if browser_running:
                    if BrowserManager.restart_browser():
                        return f"Successfully opened new {app_name} instance."
                    else:
                        return f"Failed to open new {app_name} instance."
                else:
                    if BrowserManager.launch_browser():
                        return f"Successfully opened new {app_name} instance."
                    else:
                        return f"Failed to open new {app_name} instance."

        # Check if the command/binary exists before running
        import shutil
        binary = executable.split()[0] if executable else ""
        if not binary or not shutil.which(binary):
            return f"Error: {app_name} (command: {executable}) is not installed or could not be found in PATH."

        # Execute in background (non-blocking)
        # Using a list or shell runner depending on whitespace.
        # Spawning via shell is often more robust for simple CLI launchers (like google-chrome-stable).
        exit_code, msg = CommandExecutor.run_background(executable, shell=True)
        
        if exit_code == 0:
            return f"Successfully opened {app_name} (command: {executable})."
        else:
            return f"Failed to open {app_name}: {msg}"
