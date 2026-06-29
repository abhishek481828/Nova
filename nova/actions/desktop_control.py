import re
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.executor import CommandExecutor
from nova.utils import COLOR_BOLD, COLOR_CYAN, COLOR_GREEN, COLOR_RESET, print_info

class DesktopControlAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "desktop_control"

    def _get_active_media_players(self) -> list:
        exit_code, stdout, stderr = CommandExecutor.run_shell(["busctl", "--user", "list"])
        if exit_code != 0:
            return []
        players = []
        for line in stdout.splitlines():
            parts = line.split()
            if parts and parts[0].startswith("org.mpris.MediaPlayer2"):
                players.append(parts[0])
        return players

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "").strip().lower()
        if not operation:
            return "Error: No desktop operation provided."

        if operation == "lock":
            cmd = ["dbus-send", "--type=method_call", "--dest=org.gnome.ScreenSaver", 
                   "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver.Lock"]
            exit_code, stdout, stderr = CommandExecutor.run_shell(cmd, require_confirmation=False)
            if exit_code == 0:
                return "Desktop screen locked successfully."
            else:
                return f"Failed to lock screen. Error: {stderr.strip()}"

        elif operation == "night_light":
            state = params.get("state")
            # Query current night light state
            q_code, q_stdout, q_stderr = CommandExecutor.run_shell(
                ["gsettings", "get", "org.gnome.settings-daemon.plugins.color", "night-light-enabled"]
            )
            if q_code != 0:
                return f"Failed to query night light status. Error: {q_stderr.strip()}"
            
            curr_state = q_stdout.strip().lower() == "true"
            
            # Determine new state
            target_state = False
            if state is None:
                # Toggle
                target_state = not curr_state
            elif isinstance(state, bool):
                target_state = state
            elif isinstance(state, str):
                state_str = state.strip().lower()
                if state_str in ("on", "true", "1", "enable", "active"):
                    target_state = True
                elif state_str in ("off", "false", "0", "disable", "inactive"):
                    target_state = False
                elif state_str == "toggle":
                    target_state = not curr_state
                else:
                    target_state = not curr_state
            
            state_val_str = "true" if target_state else "false"
            s_code, s_stdout, s_stderr = CommandExecutor.run_shell(
                ["gsettings", "set", "org.gnome.settings-daemon.plugins.color", "night-light-enabled", state_val_str]
            )
            if s_code == 0:
                status_str = f"{COLOR_GREEN}ENABLED{COLOR_RESET}" if target_state else f"{COLOR_CYAN}DISABLED{COLOR_RESET}"
                return f"GNOME Night Light is now {status_str}."
            else:
                return f"Failed to set night light. Error: {s_stderr.strip()}"

        elif operation == "media":
            media_cmd = params.get("media_command", "").strip().lower()
            if not media_cmd:
                return "Error: No media command provided (e.g. play, pause, next, prev, stop)."

            cmd_map = {
                "play": "Play",
                "pause": "Pause",
                "playpause": "PlayPause",
                "play/pause": "PlayPause",
                "next": "Next",
                "prev": "Previous",
                "previous": "Previous",
                "stop": "Stop"
            }

            dbus_method = cmd_map.get(media_cmd)
            if not dbus_method:
                return f"Error: Unsupported media command '{media_cmd}'. Supported: play, pause, next, prev, stop."

            players = self._get_active_media_players()
            if not players:
                return "No active media players found running."

            success_players = []
            failed_players = []
            
            for player in players:
                cmd = [
                    "dbus-send", "--type=method_call", f"--dest={player}",
                    "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{dbus_method}"
                ]
                exit_code, stdout, stderr = CommandExecutor.run_shell(cmd)
                player_short_name = player.split(".")[-1]
                if exit_code == 0:
                    success_players.append(player_short_name)
                else:
                    failed_players.append((player_short_name, stderr.strip()))

            if success_players:
                players_str = ", ".join(success_players)
                return f"Sent '{dbus_method}' command to active player(s): {COLOR_CYAN}{players_str}{COLOR_RESET}."
            else:
                err_details = "; ".join([f"{p}: {e}" for p, e in failed_players])
                return f"Failed to control media players. Details: {err_details}"

        else:
            return f"Error: Unsupported desktop operation '{operation}'."
