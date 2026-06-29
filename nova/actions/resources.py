import os
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.executor import CommandExecutor
from nova.utils import COLOR_BOLD, COLOR_CYAN, COLOR_GREEN, COLOR_RED, COLOR_YELLOW, COLOR_RESET

class ResourcesAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "system_resources"

    def execute(self, params: Dict[str, Any]) -> str:
        report = []
        report.append(f"\n{COLOR_CYAN}{COLOR_BOLD}=== SYSTEM RESOURCE MONITOR ==={COLOR_RESET}\n")

        # 1. CPU Load Averages
        try:
            with open("/proc/loadavg", "r") as f:
                load = f.read().strip().split()
                if len(load) >= 3:
                    report.append(f"{COLOR_BOLD}CPU Load Average:{COLOR_RESET}")
                    report.append(f"  - 1 min:  {COLOR_GREEN}{load[0]}{COLOR_RESET}")
                    report.append(f"  - 5 min:  {COLOR_GREEN}{load[1]}{COLOR_RESET}")
                    report.append(f"  - 15 min: {COLOR_GREEN}{load[2]}{COLOR_RESET}")
                else:
                    report.append(f"{COLOR_BOLD}CPU Load Average:{COLOR_RESET} Unknown format")
        except Exception as e:
            report.append(f"{COLOR_RED}✘ Failed to read CPU load average. Error: {e}{COLOR_RESET}")

        # 2. System Temperatures
        report.append(f"\n{COLOR_BOLD}System Temperatures:{COLOR_RESET}")
        temp_found = False
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
                                    
                                    # Highlight high temperatures
                                    temp_color = COLOR_GREEN
                                    if z_temp >= 80.0:
                                        temp_color = COLOR_RED
                                    elif z_temp >= 65.0:
                                        temp_color = COLOR_YELLOW
                                        
                                    report.append(f"  - {z_type}: {temp_color}{z_temp:.1f}°C{COLOR_RESET}")
                                    temp_found = True
                                except ValueError:
                                    pass
            if not temp_found:
                report.append("  - No thermal sensors detected.")
        except Exception as e:
            report.append(f"  - {COLOR_RED}Failed to read thermal zones. Error: {e}{COLOR_RESET}")

        # 3. Memory Usage
        report.append(f"\n{COLOR_BOLD}Memory Allocation:{COLOR_RESET}")
        exit_code, stdout, stderr = CommandExecutor.run_shell(["free", "-h"])
        if exit_code == 0:
            lines = stdout.splitlines()
            if len(lines) >= 2:
                report.append(f"  {lines[0]}")
                report.append(f"  {COLOR_CYAN}{lines[1]}{COLOR_RESET}")
                if len(lines) >= 3:
                    report.append(f"  {lines[2]}")
            else:
                report.append(f"  {stdout.strip()}")
        else:
            report.append(f"  {COLOR_RED}Failed to read memory. Error: {stderr}{COLOR_RESET}")

        # 4. Battery Status
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
                        
                        device_info = f" ({mfg} {model})" if mfg or model else ""
                        report.append(f"\n{COLOR_BOLD}Battery Status {bat}{device_info}:{COLOR_RESET}")
                        report.append(f"  - Level:  {cap_color}{cap}%{COLOR_RESET}{health_str}")
                        report.append(f"  - State:  {stat_color}{stat}{COLOR_RESET}")
                    except Exception as e:
                        report.append(f"\n{COLOR_RED}✘ Failed to read battery {bat} details: {e}{COLOR_RESET}")

        report.append("\n===============================")
        return "\n".join(report)
