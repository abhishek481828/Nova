import json
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.config import APPS_JSON_PATH
from nova.executor import CommandExecutor
from nova.logger import log_error
from nova.utils import print_info

class CloseAppAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "close_app"

    def execute(self, params: Dict[str, Any]) -> str:
        app_name = params.get("app", "").strip().lower()
        if not app_name:
            return "Error: No application name provided to close."

        # Custom process name resolution overrides
        if any(k in app_name for k in ("phone", "mirror", "connect", "scrcpy")):
            process_name = "scrcpy"
        else:
            # Load apps config
            apps_map = {}
            if APPS_JSON_PATH.exists():
                try:
                    with open(APPS_JSON_PATH, "r", encoding="utf-8") as f:
                        apps_map = json.load(f)
                except Exception as e:
                    log_error("Failed to parse apps.json configuration", e)
            
            # Resolve executable command from mapping
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
            
            # Extract first token (the binary name)
            process_name = executable.split()[0]
            
            # Substring overrides for popular applications
            if "chromium" in process_name or "chrome" in process_name:
                process_name = "chromium"
            elif "code" in process_name:
                process_name = "code"

        print_info(f"Closing application: {app_name} (process: {process_name})...")
        
        # Execute pkill -f to find and terminate matching processes
        exit_code, stdout, stderr = CommandExecutor.run_shell(["pkill", "-f", process_name])
        
        # pkill exit code meanings: 0 = match found, 1 = no match found, 2 = error
        if exit_code == 0:
            return f"Successfully closed '{app_name}' (terminated process matching '{process_name}')."
        elif exit_code == 1:
            return f"No active processes found running '{app_name}' ('{process_name}')."
        else:
            return f"Failed to close '{app_name}'. Error: {stderr}"
