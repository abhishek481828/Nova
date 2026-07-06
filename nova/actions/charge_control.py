import os
import re
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor
from nova.utils import COLOR_BOLD, COLOR_CYAN, COLOR_RESET

class ChargeControlAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "charge_control"

    def _find_charge_limit_files(self) -> list:
        """Finds all available charge threshold files under /sys/class/power_supply."""
        files = []
        battery_dir = "/sys/class/power_supply"
        if os.path.exists(battery_dir):
            batteries = [d for d in os.listdir(battery_dir) if d.startswith("BAT")]
            for bat in batteries:
                bat_path = os.path.join(battery_dir, bat)
                for filename in ["charge_control_end_threshold", "charge_control_limit_max", "charge_stop_threshold"]:
                    file_path = os.path.join(bat_path, filename)
                    if os.path.exists(file_path):
                        files.append(file_path)
        return files

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "get").strip().lower()
        level_param = params.get("level")

        # Parse level if present
        level = None
        if level_param is not None:
            try:
                if isinstance(level_param, str):
                    cleaned = re.sub(r'[^0-9.]', '', level_param)
                    level = int(float(cleaned))
                else:
                    level = int(level_param)
            except (ValueError, TypeError):
                pass

        limit_files = self._find_charge_limit_files()
        if not limit_files:
            return "Error: No charge control threshold configuration files found on this hardware."

        if operation == "get":
            # Read current values
            limit_values = []
            for file_path in limit_files:
                try:
                    with open(file_path, "r") as f:
                        val = f.read().strip()
                        limit_values.append(f"{os.path.basename(os.path.dirname(file_path))}: {val}%")
                except Exception as e:
                    limit_values.append(f"{os.path.basename(os.path.dirname(file_path))}: Failed to read ({e})")
            return f"Current Charging Limit: {COLOR_CYAN}{', '.join(limit_values)}{COLOR_RESET}"

        elif operation == "set":
            if level is None:
                return "Error: No charging limit level percentage specified to set."

            # Enforce constraints (usually 10% to 100%)
            if level < 10:
                level = 10
            elif level > 100:
                level = 100

            successes = []
            failures = []

            for file_path in limit_files:
                # Read previous limit value
                prev_val = "unknown"
                try:
                    with open(file_path, "r") as f:
                        prev_val = f.read().strip()
                except Exception:
                    pass

                bat_name = os.path.basename(os.path.dirname(file_path))
                # Write new limit using sudo fallback
                cmd = f"echo {level} | sudo tee {file_path}"
                exit_code, stdout, stderr = CommandExecutor.run_shell(
                    cmd,
                    shell=True,
                    require_confirmation=False
                )

                if exit_code == 0:
                    successes.append(f"{bat_name} set to {level}% (Previous: {prev_val}%)")
                else:
                    # Try passwordless sudo -n fallback
                    fallback_cmd = f"echo {level} | sudo -n tee {file_path}"
                    exit_code_fb, stdout_fb, stderr_fb = CommandExecutor.run_shell(
                        fallback_cmd,
                        shell=True,
                        require_confirmation=False
                    )
                    if exit_code_fb == 0:
                        successes.append(f"{bat_name} set to {level}% (via passwordless sudo, Previous: {prev_val}%)")
                    else:
                        failures.append(f"{bat_name} failed: {stderr_fb.strip() or stderr.strip()}")

            if successes:
                try:
                    from nova.core.state import StateManager
                    StateManager.set_charge_limit(level)
                except Exception:
                    pass

            if successes and not failures:
                return f"Charging limit successfully updated: {', '.join(successes)}"
            elif successes and failures:
                return f"Charging limit partially updated. Success: {', '.join(successes)}. Errors: {', '.join(failures)}"
            else:
                return f"Failed to set charging limit. Errors: {', '.join(failures)}"

        else:
            return f"Error: Unsupported charging limit operation '{operation}'."
