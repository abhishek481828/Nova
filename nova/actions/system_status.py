import os
import json
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor
from nova.utils import COLOR_BOLD, COLOR_CYAN, COLOR_GREEN, COLOR_RED, COLOR_YELLOW, COLOR_RESET

class SystemStatusAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "system_status"

    def execute(self, params: Dict[str, Any]) -> str:
        report = []
        report.append(f"\n{COLOR_CYAN}{COLOR_BOLD}=== NOVA FULL SYSTEM & SOFTWARE STATUS ==={COLOR_RESET}\n")

        import psutil

        # 1. CPU Load
        try:
            if hasattr(os, "getloadavg"):
                load = os.getloadavg()
                report.append(f"{COLOR_BOLD}CPU Load Average:{COLOR_RESET}  1m: {COLOR_GREEN}{load[0]:.2f}{COLOR_RESET} | 5m: {COLOR_GREEN}{load[1]:.2f}{COLOR_RESET} | 15m: {COLOR_GREEN}{load[2]:.2f}{COLOR_RESET}")
            else:
                cpu_pct = psutil.cpu_percent(interval=0.1)
                report.append(f"{COLOR_BOLD}CPU Utilization:{COLOR_RESET}  Total: {COLOR_GREEN}{cpu_pct}%{COLOR_RESET} ({psutil.cpu_count(logical=True)} logical cores)")
        except Exception as e:
            report.append(f"{COLOR_BOLD}CPU Load:{COLOR_RESET} {COLOR_RED}Unavailable ({e}){COLOR_RESET}")

        # 2. System Temperatures
        temp_found = False
        temps = []
        try:
            if hasattr(psutil, "sensors_temperatures"):
                st = psutil.sensors_temperatures()
                if st:
                    for name, entries in st.items():
                        for entry in entries:
                            label = entry.label or name
                            z_temp = entry.current
                            temp_color = COLOR_GREEN if z_temp < 65 else (COLOR_YELLOW if z_temp < 80 else COLOR_RED)
                            temps.append(f"{label}: {temp_color}{z_temp:.1f}°C{COLOR_RESET}")
                            temp_found = True
            
            if not temp_found and os.path.exists("/sys/class/thermal"):
                thermal_dir = "/sys/class/thermal"
                for zone in sorted(os.listdir(thermal_dir)):
                    if zone.startswith("thermal_zone"):
                        zone_path = os.path.join(thermal_dir, zone)
                        type_path = os.path.join(zone_path, "type")
                        temp_path = os.path.join(zone_path, "temp")
                        if os.path.exists(type_path) and os.path.exists(temp_path):
                            with open(type_path, "r", encoding="utf-8", errors="replace") as f_type, open(temp_path, "r", encoding="utf-8", errors="replace") as f_temp:
                                z_type = f_type.read().strip()
                                z_temp = float(f_temp.read().strip()) / 1000.0
                                temp_color = COLOR_GREEN if z_temp < 65 else (COLOR_YELLOW if z_temp < 80 else COLOR_RED)
                                temps.append(f"{z_type}: {temp_color}{z_temp:.1f}°C{COLOR_RESET}")
                                temp_found = True
            if temps:
                report.append(f"{COLOR_BOLD}Temperatures:{COLOR_RESET}  " + " | ".join(temps))
        except Exception:
            pass

        # 3. RAM usage
        try:
            vmem = psutil.virtual_memory()
            total_g = vmem.total / (1024 ** 3)
            used_g = (vmem.total - vmem.available) / (1024 ** 3)
            free_g = vmem.free / (1024 ** 3)
            avail_g = vmem.available / (1024 ** 3)
            report.append(f"{COLOR_BOLD}RAM Allocation:{COLOR_RESET}  Total: {COLOR_CYAN}{total_g:.1f}GiB{COLOR_RESET} | Used: {COLOR_CYAN}{used_g:.1f}GiB ({vmem.percent}%){COLOR_RESET} | Free: {COLOR_CYAN}{free_g:.1f}GiB{COLOR_RESET} | Avail: {COLOR_CYAN}{avail_g:.1f}GiB{COLOR_RESET}")
        except Exception as e:
            report.append(f"{COLOR_BOLD}RAM Allocation:{COLOR_RESET} {COLOR_RED}Error: {e}{COLOR_RESET}")

        # 4. Storage Usage
        try:
            disk_root = "C:\\" if os.name == "nt" else "/"
            du = psutil.disk_usage(disk_root)
            total_g = du.total / (1024 ** 3)
            used_g = du.used / (1024 ** 3)
            free_g = du.free / (1024 ** 3)
            disk_label = "C: Storage" if os.name == "nt" else "Root Storage"
            report.append(f"{COLOR_BOLD}{disk_label}:{COLOR_RESET}  Size: {COLOR_CYAN}{total_g:.1f}GiB{COLOR_RESET} | Used: {COLOR_CYAN}{used_g:.1f}GiB ({du.percent}%){COLOR_RESET} | Avail: {COLOR_CYAN}{free_g:.1f}GiB{COLOR_RESET}")
        except Exception as e:
            report.append(f"{COLOR_BOLD}Storage:{COLOR_RESET} {COLOR_RED}Error: {e}{COLOR_RESET}")

        # 5. Battery Status
        try:
            bat = psutil.sensors_battery()
            if bat:
                cap = int(bat.percent)
                cap_color = COLOR_RED if cap <= 15 else (COLOR_YELLOW if cap <= 35 else COLOR_GREEN)
                state = "Charging" if bat.power_plugged else "Discharging"
                stat_color = COLOR_GREEN if bat.power_plugged else COLOR_RESET
                report.append(f"{COLOR_BOLD}Battery:{COLOR_RESET}  Level: {cap_color}{cap}%{COLOR_RESET} | State: {stat_color}{state}{COLOR_RESET}")
            elif os.path.exists("/sys/class/power_supply"):
                battery_dir = "/sys/class/power_supply"
                batteries = [d for d in os.listdir(battery_dir) if d.startswith("BAT")]
                for b in sorted(batteries):
                    b_path = os.path.join(battery_dir, b)
                    cap_file = os.path.join(b_path, "capacity")
                    stat_file = os.path.join(b_path, "status")
                    if os.path.exists(cap_file) and os.path.exists(stat_file):
                        with open(cap_file) as fc, open(stat_file) as fs:
                            cap = fc.read().strip()
                            stat = fs.read().strip()
                            report.append(f"{COLOR_BOLD}Battery {b}:{COLOR_RESET} Level: {cap}% | State: {stat}")
        except Exception:
            pass

        import shutil

        # 6. Tailscale Connection
        if shutil.which("tailscale"):
            ts_exit, ts_out, ts_err = CommandExecutor.run_shell(["tailscale", "status"])
            if ts_exit == 0:
                laptop_ip = ""
                phone_ip = ""
                phone_hostname = ""
                for line in ts_out.splitlines():
                    parts = line.split()
                    if not parts:
                        continue
                    if any(k in line.lower() for k in ("linux", "nixos", "windows", "desktop", "laptop")):
                        laptop_ip = parts[0]
                    if "android" in line.lower():
                        phone_ip = parts[0]
                        phone_hostname = parts[1]
                
                peer_info = f" | Phone Peer: {phone_hostname} ({phone_ip})" if phone_ip else " | No Phone Peer"
                report.append(f"{COLOR_BOLD}Tailscale Link:{COLOR_RESET}  {COLOR_GREEN}ACTIVE{COLOR_RESET} | Device IP: {laptop_ip}{peer_info}")
            else:
                report.append(f"{COLOR_BOLD}Tailscale Link:{COLOR_RESET}  {COLOR_RED}INACTIVE{COLOR_RESET}")
        else:
            report.append(f"{COLOR_BOLD}Tailscale Link:{COLOR_RESET}  {COLOR_YELLOW}NOT INSTALLED{COLOR_RESET}")

        # 7. PhoneNotify Server & Connected Devices
        server_running = False
        phones_connected = 0
        extensions_connected = 0
        try:
            import httpx
            resp = httpx.get("http://localhost:8080/status", timeout=1.0)
            if resp.status_code == 200:
                server_running = True
                data = resp.json()
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
        if shutil.which("adb"):
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
        else:
            report.append(f"{COLOR_BOLD}ADB USB/TCP Link:{COLOR_RESET}  {COLOR_YELLOW}NOT INSTALLED IN PATH{COLOR_RESET}")

        report.append("\n============================================")
        return "\n".join(report)
