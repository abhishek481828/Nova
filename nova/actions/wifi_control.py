from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.executor import CommandExecutor
from nova.utils import COLOR_BOLD, COLOR_CYAN, COLOR_GREEN, COLOR_RED, COLOR_YELLOW, COLOR_RESET, print_info

class WifiControlAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "wifi_control"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "status").strip().lower()

        if operation == "status":
            r_code, r_stdout, r_stderr = CommandExecutor.run_shell(["nmcli", "radio", "wifi"])
            if r_code != 0:
                return f"Failed to check Wi-Fi radio status. Error: {r_stderr.strip()}"
            
            is_enabled = r_stdout.strip().lower() == "enabled"
            status_str = f"{COLOR_GREEN}ENABLED{COLOR_RESET}" if is_enabled else f"{COLOR_RED}DISABLED{COLOR_RESET}"
            
            report = [f"Wi-Fi Radio: {status_str}"]

            if is_enabled:
                c_code, c_stdout, c_stderr = CommandExecutor.run_shell(["nmcli", "-t", "-f", "active,ssid,signal,bars", "dev", "wifi"])
                if c_code == 0:
                    connected_ssid = None
                    signal = ""
                    bars = ""
                    for line in c_stdout.splitlines():
                        if line.startswith("yes:"):
                            # Format is: yes:SSID:SIGNAL:BARS
                            parts = line.split(":")
                            if len(parts) >= 4:
                                # In case SSID has colons, handle split carefully
                                # the list from -t is escaped, but splits generally work
                                connected_ssid = parts[1]
                                signal = parts[2]
                                bars = parts[3]
                                break
                    if connected_ssid:
                        report.append(f"Status: {COLOR_GREEN}Connected{COLOR_RESET}")
                        report.append(f"SSID: {COLOR_CYAN}{connected_ssid}{COLOR_RESET}")
                        report.append(f"Signal Strength: {COLOR_GREEN}{signal}% ({bars}){COLOR_RESET}")
                    else:
                        report.append(f"Status: {COLOR_YELLOW}Disconnected / Idle{COLOR_RESET}")
                else:
                    report.append(f"Status: Unknown (Failed to query connections: {c_stderr.strip()})")
            else:
                report.append("Status: Offline")

            return "\n".join(report)

        elif operation == "toggle":
            r_code, r_stdout, r_stderr = CommandExecutor.run_shell(["nmcli", "radio", "wifi"])
            if r_code != 0:
                return f"Failed to check Wi-Fi radio status. Error: {r_stderr.strip()}"
            
            curr_enabled = r_stdout.strip().lower() == "enabled"
            
            state = params.get("state")
            target_enabled = False
            if state is None:
                target_enabled = not curr_enabled
            elif isinstance(state, bool):
                target_enabled = state
            elif isinstance(state, str):
                state_str = state.strip().lower()
                if state_str in ("on", "true", "1", "enable", "active"):
                    target_enabled = True
                elif state_str in ("off", "false", "0", "disable", "inactive"):
                    target_enabled = False
                elif state_str == "toggle":
                    target_enabled = not curr_enabled
                else:
                    target_enabled = not curr_enabled
            
            state_val_str = "on" if target_enabled else "off"
            s_code, s_stdout, s_stderr = CommandExecutor.run_shell(["nmcli", "radio", "wifi", state_val_str])
            if s_code == 0:
                status_str = f"{COLOR_GREEN}ENABLED{COLOR_RESET}" if target_enabled else f"{COLOR_RED}DISABLED{COLOR_RESET}"
                return f"Wi-Fi radio has been successfully set to {status_str}."
            else:
                return f"Failed to toggle Wi-Fi radio. Error: {s_stderr.strip()}"

        elif operation == "scan":
            print_info("Scanning for nearby Wi-Fi networks...")
            # Trigger rescan first
            CommandExecutor.run_shell(["nmcli", "device", "wifi", "rescan"])
            s_code, s_stdout, s_stderr = CommandExecutor.run_shell(["nmcli", "-f", "SSID,SIGNAL,SECURITY,BARS", "dev", "wifi", "list"])
            if s_code != 0:
                return f"Failed to scan Wi-Fi networks. Error: {s_stderr.strip()}"
            
            lines = s_stdout.splitlines()
            if len(lines) <= 1:
                return "No nearby Wi-Fi networks found."

            # Format the output beautifully
            formatted = []
            header = lines[0]
            formatted.append(f"{COLOR_BOLD}{COLOR_CYAN}{header}{COLOR_RESET}")
            for line in lines[1:]:
                # Highlight active network if it's there (starts with '*' in general lists, 
                # but we queried specific fields, so it won't start with '*'. That's fine)
                formatted.append(line)
            return "\n".join(formatted)

        elif operation == "connect":
            ssid = params.get("ssid", "").strip()
            password = params.get("password", "").strip()

            if not ssid:
                return "Error: No Wi-Fi SSID provided to connect."

            print_info(f"Connecting to Wi-Fi network: '{ssid}'...")
            
            cmd = ["nmcli", "device", "wifi", "connect", ssid]
            if password:
                cmd.extend(["password", password])

            c_code, c_stdout, c_stderr = CommandExecutor.run_shell(cmd, require_confirmation=False)
            if c_code == 0:
                return f"Successfully connected to Wi-Fi network: {COLOR_GREEN}{ssid}{COLOR_RESET}."
            else:
                return f"Failed to connect to Wi-Fi '{ssid}'. Error: {c_stderr.strip() or c_stdout.strip()}"

        else:
            return f"Error: Unsupported Wi-Fi operation '{operation}'."
