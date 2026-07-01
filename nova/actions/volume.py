import re
from typing import Any, Dict, Tuple
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor
from nova.utils import print_info, COLOR_BOLD, COLOR_CYAN, COLOR_RESET

class VolumeControlAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "volume_control"

    def _get_current_volume(self) -> Tuple[float, bool]:
        """Queries the system for current volume. Returns (volume_float, is_muted)."""
        exit_code, stdout, stderr = CommandExecutor.run_shell(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        if exit_code != 0:
            raise RuntimeError(f"Failed to query volume: {stderr.strip()}")
            
        # Format example: "Volume: 0.44" or "Volume: 0.44 [MUTED]"
        text = stdout.strip()
        parts = text.split()
        if len(parts) >= 2:
            try:
                val = float(parts[1])
                is_muted = "[MUTED]" in text
                return val, is_muted
            except ValueError:
                pass
        raise ValueError(f"Unexpected wpctl output format: {text!r}")

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "get").strip().lower()
        level_param = params.get("level")
        
        # Parse level if present
        level = None
        if level_param is not None:
            try:
                # Handle cases like "125%" or strings
                if isinstance(level_param, str):
                    cleaned = re.sub(r'[^0-9.]', '', level_param)
                    level = int(float(cleaned))
                else:
                    level = int(level_param)
            except (ValueError, TypeError):
                pass

        try:
            if operation == "mute":
                exit_code, stdout, stderr = CommandExecutor.run_shell(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"])
                if exit_code == 0:
                    return "System audio muted successfully."
                else:
                    return f"Failed to mute audio. Error: {stderr.strip()}"

            elif operation == "unmute":
                exit_code, stdout, stderr = CommandExecutor.run_shell(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])
                if exit_code == 0:
                    return "System audio unmuted successfully."
                else:
                    return f"Failed to unmute audio. Error: {stderr.strip()}"

            elif operation == "get":
                val, is_muted = self._get_current_volume()
                pct = int(val * 100)
                muted_str = " (Muted)" if is_muted else ""
                return f"Current System Volume: {COLOR_CYAN}{pct}%{COLOR_RESET}{muted_str}"

            elif operation in ("set", "increase", "decrease"):
                # Retrieve current volume
                curr_val, is_muted = self._get_current_volume()
                curr_pct = int(curr_val * 100)

                new_pct = curr_pct
                if operation == "set":
                    new_pct = level if level is not None else 50
                elif operation == "increase":
                    step = level if level is not None else 10
                    new_pct = curr_pct + step
                elif operation == "decrease":
                    step = level if level is not None else 10
                    new_pct = curr_pct - step

                # Enforce safety constraints: 0% to 150%
                if new_pct < 0:
                    new_pct = 0
                elif new_pct > 150:
                    new_pct = 150
                    print_info("Enforcing safety limit: Audio volume cannot exceed 150%.")

                new_val_float = new_pct / 100.0

                # Set volume
                exit_code, stdout, stderr = CommandExecutor.run_shell(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{new_val_float:.2f}"])
                if exit_code != 0:
                    return f"Failed to adjust system volume. Error: {stderr.strip()}"

                # Auto-unmute if modifying volume
                if is_muted:
                    CommandExecutor.run_shell(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])

                return f"System volume set to {COLOR_CYAN}{new_pct}%{COLOR_RESET} (Previous: {curr_pct}%)"

            else:
                return f"Error: Unsupported volume operation '{operation}'."

        except Exception as e:
            return f"Error controlling system volume: {e}"
