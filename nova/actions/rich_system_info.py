import os
import re
import socket
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor
from nova.packages import NixPackageManager
from nova.utils import COLOR_BOLD, COLOR_CYAN, COLOR_GREEN, COLOR_RED, COLOR_YELLOW, COLOR_RESET

class RichSystemInfoAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "rich_system_info"

    def _strip_ansi(self, text: str) -> str:
        return re.sub(r'\x1b\[[0-9;]*m', '', text)

    def execute(self, params: Dict[str, Any]) -> str:
        import platform
        import time
        import psutil

        # 1. Collect OS info
        if os.name == "nt":
            pretty_name = f"Windows {platform.release()} (Build {platform.version()})"
        else:
            pretty_name = "Linux"
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release", "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            pretty_name = line.split("=", 1)[1].strip().strip('"')
                            break

        # 2. Collect Kernel info
        if os.name == "nt":
            kernel = platform.platform()
        else:
            k_code, k_stdout, k_stderr = CommandExecutor.run_shell(["uname", "-srm"])
            kernel = k_stdout.strip() if k_code == 0 else "Linux"

        # 3. Collect Uptime info
        uptime_str = "Unknown"
        try:
            uptime_seconds = time.time() - psutil.boot_time()
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0:
                parts.append(f"{hours}h")
            if minutes > 0 or not parts:
                parts.append(f"{minutes}m")
            uptime_str = ", ".join(parts)
        except Exception:
            pass

        # 4. Collect Shell info
        if os.name == "nt":
            shell = os.environ.get("PSExecutionPolicyPreference", None)
            shell = "PowerShell" if shell or "PSModulePath" in os.environ else os.path.basename(os.environ.get("COMSPEC", "cmd.exe"))
        else:
            shell = os.environ.get("SHELL", "/bin/bash").split("/")[-1]

        # 5. Collect DE / WM info
        if os.name == "nt":
            de = "Windows Explorer"
            wm = "Desktop Window Manager (DWM)"
        else:
            de = os.environ.get("XDG_CURRENT_DESKTOP", "GNOME")
            wm = "Mutter"

        # 6. Collect Packages count
        if os.name == "nt":
            pkgs_label = "System Packages"
            pkgs_count = "Windows Native"
            sys_pkgs_count = "winget active"
        else:
            pkgs_count = len(NixPackageManager.get_installed_packages())
            sys_pkgs_count = pkgs_count

        # 7. Collect CPU info
        cpu_model = platform.processor() or "Unknown CPU"
        if os.name != "nt" and os.path.exists("/proc/cpuinfo"):
            try:
                with open("/proc/cpuinfo", "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.strip().startswith("model name"):
                            cpu_model = line.split(":", 1)[1].strip()
                            cpu_model = re.sub(r'\s+', ' ', cpu_model)
                            break
            except Exception:
                pass

        # 8. Collect GPU info
        gpu_model = "Standard Display Adapter"
        if os.name != "nt":
            gpu_code, gpu_stdout, gpu_stderr = CommandExecutor.run_shell("lspci | grep -i -E 'vga|3d|display'", shell=True)
            if gpu_code == 0 and gpu_stdout.strip():
                first_gpu_line = gpu_stdout.splitlines()[0]
                parts = first_gpu_line.split("controller:")
                gpu_model = parts[1].strip() if len(parts) > 1 else first_gpu_line.strip()
        else:
            try:
                c_code, c_stdout, _ = CommandExecutor.run_shell(["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name | Select-Object -First 1"])
                if c_code == 0 and c_stdout.strip():
                    gpu_model = c_stdout.strip()
            except Exception:
                pass
        if len(gpu_model) > 40:
            gpu_model = gpu_model[:37] + "..."

        # 9. Collect Memory info
        mem_str = "Unknown"
        try:
            vmem = psutil.virtual_memory()
            total_gb = vmem.total / (1024 ** 3)
            used_gb = (vmem.total - vmem.available) / (1024 ** 3)
            mem_str = f"{used_gb:.1f}GiB / {total_gb:.1f}GiB ({int(vmem.percent)}%)"
        except Exception:
            pass

        # 10. Collect Disk info
        disk_str = "Unknown"
        try:
            disk_root = "C:\\" if os.name == "nt" else "/"
            du = psutil.disk_usage(disk_root)
            disk_str = f"{du.used / (1024**3):.1f}GiB / {du.total / (1024**3):.1f}GiB ({int(du.percent)}%)"
        except Exception:
            pass

        # 11. Collect Network IP info
        local_ip = "Unknown"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                pass

        public_ip = "Unknown"
        try:
            import httpx
            resp = httpx.get("https://api.ipify.org", headers={'User-Agent': 'Nova-Terminal-Agent'}, timeout=1.0)
            if resp.status_code == 200:
                public_ip = resp.text.strip()
        except Exception:
            pass

        # Get username and hostname
        username = os.environ.get("USER", os.environ.get("USERNAME", "user"))
        hostname = socket.gethostname()

        # 12. Build the output
        logo_color = COLOR_CYAN
        if os.name == "nt":
            logo = [
                f"          {logo_color}  _   _  _____  _    _        {COLOR_RESET}",
                f"          {logo_color} | \\ | |/ ____|| |  | |  /\\   {COLOR_RESET}",
                f"          {logo_color} |  \\| | |  __ | |  | | /  \\  {COLOR_RESET}",
                f"          {logo_color} | . ` | | |_ || |  | |/ /\\ \\ {COLOR_RESET}",
                f"          {logo_color} | |\\  | |__| || |__| / ____ \\{COLOR_RESET}",
                f"          {logo_color} |_| \\_|\\_____| \\____/_/    \\_\\{COLOR_RESET}",
                f"          {logo_color}        [ NOVA AI CORE ]       {COLOR_RESET}"
            ]
        else:
            logo = [
                f"          {logo_color}  [#####] ####      ####  {COLOR_RESET}",
                f"          {logo_color} [##]    ######  ######   {COLOR_RESET}",
                f"          {logo_color} [##    ##  ######  ##    {COLOR_RESET}",
                f"          {logo_color}  ##   ##    ##    ##     {COLOR_RESET}",
                f"          {logo_color}  [## ###          ###    {COLOR_RESET}",
                f"          {logo_color} [#######        ######   {COLOR_RESET}",
                f"          {logo_color}  [#####]          [##]   {COLOR_RESET}"
            ]

        # Calculate visual padding of logo lines
        logo_width = 34
        padded_logo = []
        for line in logo:
            stripped = self._strip_ansi(line)
            padding = logo_width - len(stripped)
            padded_logo.append(line + (" " * padding))

        # Format stats list
        user_host = f"{COLOR_CYAN}{COLOR_BOLD}{username}{COLOR_RESET}@{COLOR_CYAN}{COLOR_BOLD}{hostname}{COLOR_RESET}"
        separator = "-" * (len(username) + len(hostname) + 1)
        
        disk_label = "Disk (C:)" if os.name == "nt" else "Disk (/)"
        stats = [
            user_host,
            separator,
            f"{COLOR_CYAN}{COLOR_BOLD}OS{COLOR_RESET}: {pretty_name}",
            f"{COLOR_CYAN}{COLOR_BOLD}Kernel{COLOR_RESET}: {kernel}",
            f"{COLOR_CYAN}{COLOR_BOLD}Uptime{COLOR_RESET}: {uptime_str}",
            f"{COLOR_CYAN}{COLOR_BOLD}Shell{COLOR_RESET}: {shell}",
            f"{COLOR_CYAN}{COLOR_BOLD}DE{COLOR_RESET}: {de}",
            f"{COLOR_CYAN}{COLOR_BOLD}WM{COLOR_RESET}: {wm}",
            f"{COLOR_CYAN}{COLOR_BOLD}Packages{COLOR_RESET}: {pkgs_count} | {sys_pkgs_count}",
            f"{COLOR_CYAN}{COLOR_BOLD}CPU{COLOR_RESET}: {cpu_model}",
            f"{COLOR_CYAN}{COLOR_BOLD}GPU{COLOR_RESET}: {gpu_model}",
            f"{COLOR_CYAN}{COLOR_BOLD}Memory{COLOR_RESET}: {mem_str}",
            f"{COLOR_CYAN}{COLOR_BOLD}{disk_label}{COLOR_RESET}: {disk_str}",
            f"{COLOR_CYAN}{COLOR_BOLD}Local IP{COLOR_RESET}: {local_ip}",
            f"{COLOR_CYAN}{COLOR_BOLD}Public IP{COLOR_RESET}: {public_ip}"
        ]

        # Merge logo and stats side by side
        output = [""] # Start with a blank line
        max_lines = max(len(padded_logo), len(stats))
        empty_logo_padding = " " * logo_width

        for i in range(max_lines):
            logo_part = padded_logo[i] if i < len(padded_logo) else empty_logo_padding
            stat_part = stats[i] if i < len(stats) else ""
            output.append(f"{logo_part}  {stat_part}")
        
        output.append("") # End with a blank line
        return "\n".join(output)
