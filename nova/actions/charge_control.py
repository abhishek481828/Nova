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
        """Finds all available charge threshold files under /sys/class/power_supply (Linux)."""
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

        # Windows Battery & Power Handler
        if os.name == "nt":
            import psutil
            bat = psutil.sensors_battery()
            if operation == "get":
                if bat is not None:
                    plugged = "Plugged In" if bat.power_plugged else "On Battery"
                    time_info = f", ~{bat.secsleft // 60} min remaining" if bat.secsleft > 0 and not bat.power_plugged else ""
                    return f"Battery Status: {COLOR_CYAN}{bat.percent}%{COLOR_RESET} ({plugged}{time_info})"
                return "Battery Status: No battery hardware detected (Desktop/AC powered)."

            elif operation == "set":
                return (
                    "Setting hardware charging thresholds on Windows is managed by your device OEM power suite "
                    "(such as Lenovo Vantage, MyASUS, Dell Command | Power Manager, or HP Support Assistant)."
                )
            else:
                return f"Error: Unsupported charging operation '{operation}' on Windows."

        # Linux Charging Limit Handler
        limit_files = self._find_charge_limit_files()
        if not limit_files:
            return "Error: No charge control threshold configuration files found on this hardware."

        if operation == "get":
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

            level = max(10, min(100, level))
            successes = []
            failures = []

            for file_path in limit_files:
                bat_name = os.path.basename(os.path.dirname(file_path))
                cmd = f"echo {level} | sudo tee {file_path}"
                exit_code, stdout, stderr = CommandExecutor.run_shell(
                    cmd, shell=True, require_confirmation=False
                )
                if exit_code == 0:
                    successes.append(f"{bat_name} set to {level}%")
                else:
                    failures.append(f"{bat_name} failed: {stderr.strip()}")

            if successes and not failures:
                return f"Charging limit successfully updated: {', '.join(successes)}"
            elif successes and failures:
                return f"Charging limit partially updated. Success: {', '.join(successes)}. Errors: {', '.join(failures)}"
            else:
                return f"Failed to set charging limit: {', '.join(failures)}"

        return f"Error: Unsupported charging limit operation '{operation}'."
