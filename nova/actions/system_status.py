import os
import json
import urllib.request
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.executor import CommandExecutor
from nova.utils import COLOR_BOLD, COLOR_CYAN, COLOR_GREEN, COLOR_RED, COLOR_YELLOW, COLOR_RESET

class SystemStatusAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "system_status"

    def execute(self, params: Dict[str, Any]) -> str:
        report = []
        report.append(f"\n{COLOR_CYAN}{COLOR_BOLD}=== NOVA FULL SYSTEM & SOFTWARE STATUS ==={COLOR_RESET}\n")

        # 1. CPU Load Average
        try:
            with open("/proc/loadavg", "r") as f:
                load = f.read().strip().split()
                if len(load) >= 3:
                    report.append(f"{COLOR_BOLD}CPU Load Average:{COLOR_RESET}  1m: {COLOR_GREEN}{load[0]}{COLOR_RESET} | 5m: {COLOR_GREEN}{load[1]}{COLOR_RESET} | 15m: {COLOR_GREEN}{load[2]}{COLOR_RESET}")
                else:
                    report.append(f"{COLOR_BOLD}CPU Load Average:{COLOR_RESET} Unknown")
        except Exception as e:
            report.append(f"{COLOR_BOLD}CPU Load Average:{COLOR_RESET} {COLOR_RED}Failed to read: {e}{COLOR_RESET}")

        # 2. System Temperatures
        temp_found = False
        temps = []
        try:
            thermal_dir = "/sys/class/thermal"
            if os.path.exists(thermal_dir):
                for zone in sorted(os.listdir(thermal_dir)):
                    if zone.startswith("thermal_zone"):
                        zone_path = os.path.join(thermal_dir, zone)
                        type_path = os.path.join(zone_path, "type")
                        temp_path = os.path.join(zone_path, "temp")
                        
                        if os.path.exists(type_path) and os.path.exists(temp_path):
                            with open(type_path, "r") as f_type, open(temp_path, "r") as f_temp:
                                z_type = f_type.read().strip()
                                z_temp_raw = f_temp.read().strip()
                                try:
                                    z_temp = float(z_temp_raw) / 1000.0
                                    temp_color = COLOR_GREEN
                                    if z_temp >= 80.0:
                                        temp_color = COLOR_RED
                                    elif z_temp >= 65.0:
                                        temp_color = COLOR_YELLOW
                                    temps.append(f"{z_type}: {temp_color}{z_temp:.1f}°C{COLOR_RESET}")
                                    temp_found = True
                                except ValueError:
                                    pass
            if temps:
                report.append(f"{COLOR_BOLD}Temperatures:{COLOR_RESET}  " + " | ".join(temps))
        except Exception:
            pass

        # 3. RAM usage
        exit_code, stdout, stderr = CommandExecutor.run_shell(["free", "-h"])
        if exit_code == 0:
            lines = stdout.splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    report.append(f"{COLOR_BOLD}RAM Allocation:{COLOR_RESET}  Total: {COLOR_CYAN}{parts[1]}{COLOR_RESET} | Used: {COLOR_CYAN}{parts[2]}{COLOR_RESET} | Free: {COLOR_CYAN}{parts[3]}{COLOR_RESET} | Avail: {COLOR_CYAN}{parts[6] if len(parts) > 6 else parts[3]}{COLOR_RESET}")
        else:
            report.append(f"{COLOR_BOLD}RAM Allocation:{COLOR_RESET} {COLOR_RED}Error: {stderr.strip()}{COLOR_RESET}")

        # 4. Storage Usage
        exit_code, stdout, stderr = CommandExecutor.run_shell(["df", "-h", "/"])
        if exit_code == 0:
            lines = stdout.splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    report.append(f"{COLOR_BOLD}Root Storage:{COLOR_RESET}  Size: {COLOR_CYAN}{parts[1]}{COLOR_RESET} | Used: {COLOR_CYAN}{parts[2]} ({parts[4]}){COLOR_RESET} | Avail: {COLOR_CYAN}{parts[3]}{COLOR_RESET}")
        else:
            report.append(f"{COLOR_BOLD}Root Storage:{COLOR_RESET} {COLOR_RED}Error: {stderr.strip()}{COLOR_RESET}")

        # 5. Battery Status
        battery_dir = "/sys/class/power_supply"
        if os.path.exists(battery_dir):
            batteries = [d for d in os.listdir(battery_dir) if d.startswith("BAT")]
            for bat in sorted(batteries):
                bat_path = os.path.join(battery_dir, bat)
                cap_path = os.path.join(bat_path, "capacity")
                stat_path = os.path.join(bat_path, "status")
                model_path = os.path.join(bat_path, "model_name")
                mfg_path = os.path.join(bat_path, "manufacturer")
                health_full = os.path.join(bat_path, "energy_full")
                health_design = os.path.join(bat_path, "energy_full_design")
                
                if not os.path.exists(health_full):
                    health_full = os.path.join(bat_path, "charge_full")
                if not os.path.exists(health_design):
                    health_design = os.path.join(bat_path, "charge_full_design")
                
                if os.path.exists(cap_path) and os.path.exists(stat_path):
                    try:
                        with open(cap_path, "r") as f_cap, open(stat_path, "r") as f_stat:
                            cap = f_cap.read().strip()
                            stat = f_stat.read().strip()
                        
                        model = ""
                        if os.path.exists(model_path):
                            with open(model_path, "r") as f_model:
                                model = f_model.read().strip()
                                
                        mfg = ""
                        if os.path.exists(mfg_path):
                            with open(mfg_path, "r") as f_mfg:
                                mfg = f_mfg.read().strip()
                                
                        health_str = ""
                        if os.path.exists(health_full) and os.path.exists(health_design):
                            with open(health_full, "r") as f_full, open(health_design, "r") as f_design:
                                full_val = float(f_full.read().strip())
                                design_val = float(f_design.read().strip())
                                if design_val > 0:
                                    health_pct = (full_val / design_val) * 100.0
                                    health_str = f" (Health: {health_pct:.1f}%)"
                        
                        cap_val = int(cap)
                        cap_color = COLOR_GREEN
                        if cap_val <= 15:
                            cap_color = COLOR_RED
                        elif cap_val <= 35:
                            cap_color = COLOR_YELLOW
                            
                        stat_color = COLOR_GREEN if stat == "Charging" else (COLOR_CYAN if stat == "Full" else COLOR_RESET)
                        
                        device_info = f" {mfg} {model}".strip()
                        bat_label = f" ({device_info})" if device_info else ""
                        report.append(f"{COLOR_BOLD}Battery {bat}{bat_label}:{COLOR_RESET}  Level: {cap_color}{cap}%{COLOR_RESET}{health_str} | State: {stat_color}{stat}{COLOR_RESET}")
                    except Exception:
                        pass

        # 6. Tailscale Connection
        ts_exit, ts_out, ts_err = CommandExecutor.run_shell(["tailscale", "status"])
        if ts_exit == 0:
            laptop_ip = ""
            phone_ip = ""
            phone_hostname = ""
            for line in ts_out.splitlines():
                parts = line.split()
                if not parts:
                    continue
                if "linux" in line or "nixos" in line:
                    laptop_ip = parts[0]
                if "android" in line:
                    phone_ip = parts[0]
                    phone_hostname = parts[1]
            
            peer_info = f" | Phone Peer: {phone_hostname} ({phone_ip})" if phone_ip else " | No Phone Peer"
            report.append(f"{COLOR_BOLD}Tailscale Link:{COLOR_RESET}  {COLOR_GREEN}ACTIVE{COLOR_RESET} | Laptop IP: {laptop_ip}{peer_info}")
        else:
            report.append(f"{COLOR_BOLD}Tailscale Link:{COLOR_RESET}  {COLOR_RED}INACTIVE{COLOR_RESET}")

        # 7. PhoneNotify Server & Connected Devices
        server_running = False
        phones_connected = 0
        extensions_connected = 0
        try:
            with urllib.request.urlopen("http://localhost:8080/status", timeout=1.5) as response:
                if response.status == 200:
                    server_running = True
                    data = json.loads(response.read().decode("utf-8"))
                    conns = data.get("connections", {})
                    phones_connected = conns.get("phones", 0)
                    extensions_connected = conns.get("extensions", 0)
        except Exception:
            pass

        if server_running:
            report.append(f"{COLOR_BOLD}PhoneNotify Server:{COLOR_RESET} {COLOR_GREEN}ACTIVE{COLOR_RESET} | Phones: {COLOR_CYAN}{phones_connected}{COLOR_RESET} | Extensions: {COLOR_CYAN}{extensions_connected}{COLOR_RESET}")
        else:
            report.append(f"{COLOR_BOLD}PhoneNotify Server:{COLOR_RESET} {COLOR_RED}INACTIVE{COLOR_RESET}")

        # 8. ADB Connection
        adb_exit, adb_out, adb_err = CommandExecutor.run_shell(["adb", "devices"])
        if adb_exit == 0:
            devices = []
            for line in adb_out.splitlines():
                if "devices attached" in line or not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    devices.append(parts[0])
            
            dev_str = ", ".join(devices) if devices else "None"
            report.append(f"{COLOR_BOLD}ADB USB/TCP Link:{COLOR_RESET}  Devices connected: {COLOR_GREEN if devices else COLOR_RESET}{dev_str}{COLOR_RESET}")
        else:
            report.append(f"{COLOR_BOLD}ADB USB/TCP Link:{COLOR_RESET}  {COLOR_RED}ERROR (exit {adb_exit}){COLOR_RESET}")

        report.append("\n============================================")
        return "\n".join(report)
