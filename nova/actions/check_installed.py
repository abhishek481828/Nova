import os
import shutil
import subprocess
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.packages import PackageManager
from nova.utils import print_info

class CheckInstalledAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "check_installed"

    def execute(self, params: Dict[str, Any]) -> str:
        package = params.get("package", "").strip()
        if not package:
            return "Error: No package name specified to check."

        pkg_clean = package.lower().replace("-", "").replace("_", "").replace(" ", "")

        # Intercept Cloudflare Warp VPN status checks
        if pkg_clean in ("warp", "warpvpn", "cloudflarewarp", "cloudflarewarpvpn"):
            return check_warp_status()

        print_info(f"Checking if '{package}' is installed on your device...")

        # Check 1: Package Manager List (winget on Windows, nix on Linux)
        try:
            installed = PackageManager.get_installed_packages()
            matches = [name for name in installed if package.lower() in name.lower()]
            if matches:
                return f"Yes, '{package}' is installed on your device (found: {', '.join(matches[:3])})."
        except Exception:
            pass

        # Check 2: Binary Search in system PATH
        aliases = [
            package,
            package.lower(),
            package.replace(" ", "-").lower(),
            f"{package.lower()}-cli",
            f"{package.lower()}-app",
            f"{package.lower()}.exe"
        ]

        # Specific alias overrides for popular desktop apps
        if "chrome" in package.lower() or "chromium" in package.lower():
            aliases.extend(["chrome", "chromium", "google-chrome-stable", "google-chrome"])
        if "vscode" in package.lower() or "code" in package.lower():
            aliases.extend(["code", "vscodium", "vscode"])
        if "terminal" in package.lower():
            aliases.extend(["wt", "powershell", "cmd"])
        if "notepad" in package.lower():
            aliases.append("notepad")

        for alias in aliases:
            path = shutil.which(alias)
            if path:
                return f"Yes, '{package}' is installed on your device (found binary: {path})."

        # Check 3: Windows Service / Systemctl Service check
        if os.name == "nt":
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", f"Get-Service -Name *{package}* -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"],
                    capture_output=True, text=True, check=False
                )
                svc = res.stdout.strip()
                if svc:
                    return f"Yes, '{package}' matches an installed system service ({svc})."
            except Exception:
                pass
        else:
            try:
                res = subprocess.run(
                    ["systemctl", "list-units", "--type=service", "--all", f"*{package.lower()}*"],
                    capture_output=True, text=True, check=False
                )
                if res.returncode == 0 and package.lower() in res.stdout.lower():
                    return f"Yes, '{package}' matches a system service configured on your device."
            except Exception:
                pass

        return f"No, '{package}' does not appear to be installed on your device."


def check_warp_status() -> str:
    # 1. Check if warp-cli is installed
    if not shutil.which("warp-cli"):
        return (
            "Cloudflare Warp (warp-cli) is not installed on your device.\n"
            "You can install it using: 'winget install Cloudflare.Warp' on Windows."
        )

    # 2. Query status
    res = subprocess.run(
        ["warp-cli", "status"],
        capture_output=True,
        text=True,
        check=False
    )
    output = res.stdout.strip() + "\n" + res.stderr.strip()

    if "Connected" in output:
        return "Status: Cloudflare Warp is CONNECTED and active!"
    elif "Disconnected" in output:
        return (
            "Status: Cloudflare Warp is DISCONNECTED.\n"
            "Connect by running: warp-cli connect"
        )
    else:
        lines = [line.strip() for line in output.splitlines() if line.strip() and ("Status" in line or "Connected" in line or "Disconnected" in line)]
        if lines:
            return f"Cloudflare Warp Status: {', '.join(lines)}"
        return f"Cloudflare Warp Status:\n{output.strip()}"
