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
        # 1. Collect OS info
        pretty_name = "NixOS"
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        pretty_name = line.split("=", 1)[1].strip().strip('"')
                        break

        # 2. Collect Kernel info
        k_code, k_stdout, k_stderr = CommandExecutor.run_shell(["uname", "-srm"])
        kernel = k_stdout.strip() if k_code == 0 else "Linux"

        # 3. Collect Uptime info
        uptime_str = "Unknown"
        if os.path.exists("/proc/uptime"):
            try:
                with open("/proc/uptime", "r") as f:
                    uptime_seconds = float(f.readline().split()[0])
                    days = int(uptime_seconds // (24 * 3600))
                    hours = int((uptime_seconds % (24 * 3600)) // 3600)
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
        shell = os.environ.get("SHELL", "/bin/bash").split("/")[-1]

        # 5. Collect DE info
        de = os.environ.get("XDG_CURRENT_DESKTOP", "GNOME")

        # 6. Collect Packages count
        pkgs_count = len(NixPackageManager.get_installed_packages())
        sys_pkgs_count = 0
        
        # Read nova-packages.nix to count system packages
        from nova.nixos_editor import NOVA_PACKAGES_PATH, get_system_packages
        if os.path.exists(NOVA_PACKAGES_PATH):
            try:
                with open(NOVA_PACKAGES_PATH, "r", encoding="utf-8") as f:
                    content = f.read()
                    sys_pkgs_count = len(get_system_packages(content))
            except Exception:
                pass

        # 7. Collect CPU info
        cpu_model = "Unknown CPU"
        if os.path.exists("/proc/cpuinfo"):
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if line.strip().startswith("model name"):
                            cpu_model = line.split(":", 1)[1].strip()
                            cpu_model = re.sub(r'\s+', ' ', cpu_model)
                            break
            except Exception:
                pass

        # 8. Collect GPU info
        gpu_model = "Unknown GPU"
        gpu_code, gpu_stdout, gpu_stderr = CommandExecutor.run_shell("lspci | grep -i -E 'vga|3d|display'", shell=True)
        if gpu_code == 0 and gpu_stdout.strip():
            first_gpu_line = gpu_stdout.splitlines()[0]
            parts = first_gpu_line.split("controller:")
            if len(parts) > 1:
                gpu_model = parts[1].strip()
            else:
                parts = first_gpu_line.split(":")
                if len(parts) > 2:
                    gpu_model = parts[2].strip()
                else:
                    gpu_model = first_gpu_line.strip()
            # Truncate overly long GPU strings
            if len(gpu_model) > 40:
                gpu_model = gpu_model[:37] + "..."

        # 9. Collect Memory info
        mem_str = "Unknown"
        if os.path.exists("/proc/meminfo"):
            try:
                meminfo = {}
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            meminfo[parts[0].rstrip(":")] = int(parts[1])
                total_kb = meminfo.get("MemTotal", 0)
                avail_kb = meminfo.get("MemAvailable", total_kb)
                used_kb = total_kb - avail_kb
                
                total_gb = total_kb / (1024 * 1024)
                used_gb = used_kb / (1024 * 1024)
                pct = (used_kb / total_kb) * 100 if total_kb > 0 else 0
                mem_str = f"{used_gb:.1f}GiB / {total_gb:.1f}GiB ({int(pct)}%)"
            except Exception:
                pass

        # 10. Collect Disk info
        disk_str = "Unknown"
        disk_code, disk_stdout, disk_stderr = CommandExecutor.run_shell(["df", "-h", "/"])
        if disk_code == 0:
            lines = disk_stdout.splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    disk_str = f"{parts[2]} / {parts[1]} ({parts[4]})"

        # 11. Collect Network IP info
        local_ip = "Unknown"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            # Doesn't need to connect, just resolves local routing interface
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
        username = os.environ.get("USER", "nixos")
        hostname = socket.gethostname()

        # 12. Build the output
        logo_color = COLOR_CYAN
        logo = [
            f"          {logo_color}  ▗▄▄▄▖ ▄▄▄▄      ▄▄▄▄  {COLOR_RESET}",
            f"          {logo_color} ▗██▀    ████▄  ▄████▀  {COLOR_RESET}",
            f"          {logo_color} ▐██    ██ ▀████▀ ██    {COLOR_RESET}",
            f"          {logo_color}  ██   ██    ▀▀    ██   {COLOR_RESET}",
            f"          {logo_color}  ▐██ ▄██          ██▄  {COLOR_RESET}",
            f"          {logo_color} ▗▄█████▄▄        ▄▄███  {COLOR_RESET}",
            f"          {logo_color} ▝▀▀▀▀▀▀▀▀        ▀▀▀▀▀  {COLOR_RESET}"
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
        
        stats = [
            user_host,
            separator,
            f"{COLOR_CYAN}{COLOR_BOLD}OS{COLOR_RESET}: {pretty_name}",
            f"{COLOR_CYAN}{COLOR_BOLD}Kernel{COLOR_RESET}: {kernel}",
            f"{COLOR_CYAN}{COLOR_BOLD}Uptime{COLOR_RESET}: {uptime_str}",
            f"{COLOR_CYAN}{COLOR_BOLD}Shell{COLOR_RESET}: {shell}",
            f"{COLOR_CYAN}{COLOR_BOLD}DE{COLOR_RESET}: {de}",
            f"{COLOR_CYAN}{COLOR_BOLD}WM{COLOR_RESET}: Mutter",
            f"{COLOR_CYAN}{COLOR_BOLD}Packages{COLOR_RESET}: {pkgs_count} (nix-profile) | {sys_pkgs_count} (system)",
            f"{COLOR_CYAN}{COLOR_BOLD}CPU{COLOR_RESET}: {cpu_model}",
            f"{COLOR_CYAN}{COLOR_BOLD}GPU{COLOR_RESET}: {gpu_model}",
            f"{COLOR_CYAN}{COLOR_BOLD}Memory{COLOR_RESET}: {mem_str}",
            f"{COLOR_CYAN}{COLOR_BOLD}Disk (/) {COLOR_RESET}: {disk_str}",
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
