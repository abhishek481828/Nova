import os
import shutil
import subprocess
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.packages import NixPackageManager
from nova.utils import print_info

class CheckInstalledAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "check_installed"

    def execute(self, params: Dict[str, Any]) -> str:
        package = params.get("package", "").strip()
        if not package:
            return "Error: No package name specified to check."

        # Intercept PhoneNotify project checks
        pkg_clean = package.lower().replace("-", "").replace("_", "").replace(" ", "")
        if pkg_clean in ("phonenotify", "phonnotify", "phonenofity"):
            package = "phonenotify"
            return check_phone_notify_status()

        # Intercept Cloudflare Warp VPN status checks
        if pkg_clean in ("warp", "warpvpn", "cloudflarewarp", "cloudflarewarpvpn"):
            package = "warp vpn"
            return check_warp_status()

        print_info(f"Checking if '{package}' is installed on your device...")

        # Check 1: User Nix Profile List
        installed = NixPackageManager.get_installed_packages()
        nix_matches = [name for name in installed if package.lower() in name.lower()]
        if nix_matches:
            return f"Yes, '{package}' is installed in your Nix user profile (found: {', '.join(nix_matches)})."

        # Check 2: Binary Search in system PATH
        aliases = [
            package,
            package.lower(),
            package.replace(" ", "-").lower(),
            f"{package.lower()}-cli",
            f"{package.lower()}-app"
        ]

        # Specific alias overrides for popular desktop apps
        if "warp" in package.lower():
            aliases.extend(["warp-cli", "cloudflare-warp"])
        if "chrome" in package.lower() or "chromium" in package.lower():
            aliases.extend(["chromium", "google-chrome-stable", "google-chrome"])
        if "vscode" in package.lower() or "code" in package.lower():
            aliases.extend(["code", "vscodium", "vscode"])
        if "android studio" in package.lower():
            aliases.append("android-studio")

        for alias in aliases:
            path = shutil.which(alias)
            if path:
                return f"Yes, '{package}' is installed on your device (found binary: {path})."

        # Check 3: Check systemctl service matching
        try:
            # Look for active system services containing the package name
            result = subprocess.run(
                ["systemctl", "list-units", "--type=service", "--all", f"*{package.lower()}*"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0 and package.lower() in result.stdout.lower():
                return f"Yes, '{package}' matches a system service configured on your device."
        except Exception:
            pass

        return f"No, '{package}' does not appear to be installed on your device."

def check_phone_notify_status() -> str:
    import subprocess
    from nova.core.state import StateManager
    from nova.utils import print_info
    
    # Check user service status
    user_status = "inactive"
    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-active", "phone-notify.service"],
            capture_output=True,
            text=True,
            check=False
        )
        user_status = res.stdout.strip()
    except Exception:
        pass

    # Check system-wide service status
    system_status = "inactive"
    try:
        res = subprocess.run(
            ["systemctl", "is-active", "phone-notify.service"],
            capture_output=True,
            text=True,
            check=False
        )
        system_status = res.stdout.strip()
    except Exception:
        pass
        
    is_active = (user_status == "active" or system_status == "active")
    
    # Proactive Decision if Autonomous Mode is enabled
    proactive_started = False
    if not is_active and StateManager.is_autonomous():
        print_info("Proactive Decision: PhoneNotify server is currently OFF. Starting it for you...")
        try:
            # Attempt starting as user service
            subprocess.run(
                ["systemctl", "--user", "start", "phone-notify.service"],
                capture_output=True,
                check=False
            )
            # Re-check user status
            res = subprocess.run(
                ["systemctl", "--user", "is-active", "phone-notify.service"],
                capture_output=True,
                text=True,
                check=False
            )
            if res.stdout.strip() == "active":
                is_active = True
                proactive_started = True
        except Exception:
            pass
            
    description = (
        "PhoneNotify is your custom Android-to-Chromium notification synchronization relay server project.\n"
        "The project source code is located at: /home/nixos/Projects/PhoneNotify"
    )
    
    if is_active:
        if proactive_started:
            status_msg = "✅ Status: PhoneNotify server was OFF, but Nova has started it for you. It is now active!"
        else:
            status_msg = "✅ Status: The PhoneNotify server is currently ON and active!"
    else:
        status_msg = (
            "❌ Status: The PhoneNotify server is currently OFF / INACTIVE.\n"
            "Possible Solution: You can start the PhoneNotify server by running:\n"
            "  systemctl --user start phone-notify.service\n"
            "  (or sudo systemctl start phone-notify.service if configured as a system service)"
        )
        
    return f"{description}\n\n{status_msg}"

def check_warp_status() -> str:
    import shutil
    import subprocess
    from nova.core.state import StateManager
    from nova.utils import print_info
    
    # 1. Check if warp-cli is installed
    if not shutil.which("warp-cli"):
        return (
            "Cloudflare Warp (warp-cli) is not installed on your device.\n"
            "Possible Solution: You can install it using: 'nova install cloudflare-warp'."
        )
        
    # 2. Query status
    res = subprocess.run(
        ["warp-cli", "status"],
        capture_output=True,
        text=True,
        check=False
    )
    output = res.stdout.strip() + "\n" + res.stderr.strip()
    
    # Check if daemon is not running
    if "Unable to connect to the CloudflareWARP daemon" in output or "daemon" in output.lower():
        if StateManager.is_autonomous():
            print_info("Proactive Decision: Cloudflare WARP daemon is off. Attempting to start it...")
            # Attempt to start the warp-taskbar user service which runs it in user context
            subprocess.Popen(
                ["systemctl", "--user", "start", "warp-taskbar.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True
            )
            # Wait 2 seconds
            import time
            time.sleep(2)
            # Recheck status
            res = subprocess.run(
                ["warp-cli", "status"],
                capture_output=True,
                text=True,
                check=False
            )
            output = res.stdout.strip() + "\n" + res.stderr.strip()
            
    if "Unable to connect to the CloudflareWARP daemon" in output:
        return (
            "❌ Status: Cloudflare Warp daemon (warp-svc) is currently offline / not running.\n"
            "How to solve:\n"
            "  1. Start the Warp service by running:\n"
            "     systemctl --user start warp-taskbar.service\n"
            "     (or run 'sudo warp-svc' in a separate terminal)"
        )
        
    # Parse warp-cli status
    if "Connected" in output:
        return "✅ Status: Cloudflare Warp is CONNECTED and active!"
    elif "Disconnected" in output:
        return (
            "❌ Status: Cloudflare Warp is DISCONNECTED.\n"
            "How to solve: Connect to Warp VPN by running:\n"
            "  warp-cli connect"
        )
    else:
        # Return clean status
        lines = [line.strip() for line in output.splitlines() if line.strip() and "Status update" in line or "Connected" in line or "Disconnected" in line]
        if lines:
            return f"Cloudflare Warp Status: {', '.join(lines)}"
        return f"Cloudflare Warp Status:\n{output.strip()}"
