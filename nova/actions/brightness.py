import os
import re
from typing import Any, Dict, Tuple
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor
from nova.utils import print_info, print_warning, COLOR_BOLD, COLOR_CYAN, COLOR_RESET

class BrightnessControlAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "brightness_control"

    def _get_brightness_dbus(self) -> int:
        """Reads current brightness level (percentage) via D-Bus."""
        cmd = [
            "gdbus", "call", "--session",
            "--dest", "org.gnome.SettingsDaemon.Power",
            "--object-path", "/org/gnome/SettingsDaemon/Power",
            "--method", "org.freedesktop.DBus.Properties.Get",
            "org.gnome.SettingsDaemon.Power.Screen", "Brightness"
        ]
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            cmd,
            shell=False,
            require_confirmation=False
        )
        if exit_code != 0:
            raise RuntimeError(f"D-Bus call failed: {stderr.strip()}")
        
        match = re.search(r'<\s*([0-9]+)\s*>', stdout)
        if not match:
            raise ValueError(f"Could not parse D-Bus output: {stdout.strip()}")
        
        return int(match.group(1))

    def _set_brightness_dbus(self, pct: int) -> bool:
        """Sets brightness level (percentage) via D-Bus."""
        cmd = [
            "gdbus", "call", "--session",
            "--dest", "org.gnome.SettingsDaemon.Power",
            "--object-path", "/org/gnome/SettingsDaemon/Power",
            "--method", "org.freedesktop.DBus.Properties.Set",
            "org.gnome.SettingsDaemon.Power.Screen", "Brightness",
            f"<int32 {pct}>"
        ]
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            cmd,
            shell=False,
            require_confirmation=False
        )
        if exit_code != 0:
            raise RuntimeError(f"D-Bus call failed: {stderr.strip()}")
        return True

    def _get_backlight_device(self) -> str:
        """Finds the first available backlight device under /sys/class/backlight."""
        backlight_dir = "/sys/class/backlight"
        if os.path.exists(backlight_dir):
            devices = sorted(os.listdir(backlight_dir))
            if devices:
                return devices[0]
        raise RuntimeError("No backlight device found under /sys/class/backlight.")

    def _get_brightness_values(self, device: str) -> Tuple[int, int]:
        """Reads (current_raw, max_raw) values from backlight device sysfs files."""
        device_path = os.path.join("/sys/class/backlight", device)
        cur_file = os.path.join(device_path, "brightness")
        max_file = os.path.join(device_path, "max_brightness")

        if not os.path.exists(cur_file) or not os.path.exists(max_file):
            raise FileNotFoundError(f"Missing brightness configuration files under {device_path}")

        try:
            with open(cur_file, "r") as f_cur, open(max_file, "r") as f_max:
                cur_raw = int(f_cur.read().strip())
                max_raw = int(f_max.read().strip())
                return cur_raw, max_raw
        except Exception as e:
            raise RuntimeError(f"Failed to read brightness settings: {e}")

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

        # Try D-Bus method first
        try:
            curr_pct = self._get_brightness_dbus()

            if operation == "get":
                return f"Current Screen Brightness: {COLOR_CYAN}{curr_pct}%{COLOR_RESET} (D-Bus)"

            elif operation in ("set", "increase", "decrease"):
                new_pct = curr_pct
                if operation == "set":
                    new_pct = level if level is not None else 50
                elif operation == "increase":
                    step = level if level is not None else 10
                    new_pct = curr_pct + step
                elif operation == "decrease":
                    step = level if level is not None else 10
                    new_pct = curr_pct - step

                # Enforce bounds: min 5% (prevent blackout), max 100%
                if new_pct < 5:
                    new_pct = 5
                    print_warning("Enforcing safety limit: Screen brightness cannot be lowered below 5% to prevent total screen blackout.")
                elif new_pct > 100:
                    new_pct = 100

                self._set_brightness_dbus(new_pct)
                return f"Screen brightness set to {COLOR_CYAN}{new_pct}%{COLOR_RESET} (Previous: {curr_pct}%)"
            else:
                return f"Error: Unsupported brightness operation '{operation}'."

        except Exception as dbus_err:
            # Fallback to sysfs method
            print_warning(f"D-Bus brightness control unavailable ({dbus_err}). Falling back to sysfs method...")
            try:
                device = self._get_backlight_device()
                cur_raw, max_raw = self._get_brightness_values(device)

                if max_raw <= 0:
                    return "Error: Invalid hardware maximum brightness level."

                curr_pct = int((cur_raw / max_raw) * 100)

                if operation == "get":
                    return f"Current Screen Brightness: {COLOR_CYAN}{curr_pct}%{COLOR_RESET} (Device: {device})"

                elif operation in ("set", "increase", "decrease"):
                    new_pct = curr_pct
                    if operation == "set":
                        new_pct = level if level is not None else 50
                    elif operation == "increase":
                        step = level if level is not None else 10
                        new_pct = curr_pct + step
                    elif operation == "decrease":
                        step = level if level is not None else 10
                        new_pct = curr_pct - step

                    # Enforce bounds: min 5% (prevent blackout), max 100%
                    if new_pct < 5:
                        new_pct = 5
                        print_warning("Enforcing safety limit: Screen brightness cannot be lowered below 5% to prevent total screen blackout.")
                    elif new_pct > 100:
                        new_pct = 100

                    new_raw = int((new_pct / 100.0) * max_raw)
                    brightness_file = os.path.join("/sys/class/backlight", device, "brightness")

                    # Build sudo command to write value
                    cmd = f"echo {new_raw} | sudo tee {brightness_file}"

                    # Execute without confirmation
                    exit_code, stdout, stderr = CommandExecutor.run_shell(
                        cmd,
                        shell=True,
                        require_confirmation=False
                    )

                    if exit_code == 0:
                        return f"Screen brightness set to {COLOR_CYAN}{new_pct}%{COLOR_RESET} (Previous: {curr_pct}%)"
                    elif exit_code == -1:
                        return "Brightness adjustment cancelled by user."
                    else:
                        return f"Failed to adjust screen brightness. Error: {stderr.strip()}"

                else:
                    return f"Error: Unsupported brightness operation '{operation}'."

            except Exception as sysfs_err:
                return f"Error controlling screen brightness: {sysfs_err}"
