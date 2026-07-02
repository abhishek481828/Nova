import json
import re
from typing import Any, Dict, List, Tuple
from nova.actions.base import BaseAction
from nova.core.executor import CommandExecutor
from nova.utils import (
    COLOR_BOLD,
    COLOR_CYAN,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    COLOR_RESET,
    print_info
)

class DiagnoseAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "diagnose"

    def execute(self, params: Dict[str, Any]) -> str:
        print_info("Starting full system diagnostics check...")
        
        report = []
        report.append(f"\n{COLOR_CYAN}{COLOR_BOLD}=== NOVA CONNECTION DIAGNOSTICS REPORT ==={COLOR_RESET}\n")

        # ── Check 1: Tailscale Status ──
        from nova.core.state import StateManager
        ts_exit, ts_out, ts_err = CommandExecutor.run_shell(["tailscale", "status"])
        
        # Proactive Decision if Autonomous Mode is enabled and Tailscale is down
        if ts_exit != 0 and StateManager.is_autonomous():
            print_info("Proactive Decision: Tailscale is stopped. Attempting to start Tailscale...")
            # Run start command (requesting confirmation for system modification)
            CommandExecutor.run_shell(
                ["sudo", "systemctl", "start", "tailscaled"],
                require_confirmation=True,
                confirm_message="Start tailscaled service"
            )
            # Recheck status
            ts_exit, ts_out, ts_err = CommandExecutor.run_shell(["tailscale", "status"])

        ts_connected = False
        laptop_ip = ""
        phone_ip = ""
        phone_hostname = ""
        
        if ts_exit == 0:
            ts_connected = True
            report.append(f"{COLOR_GREEN}✔ Tailscale Status: CONNECTED (Auto-started if stopped){COLOR_RESET}" if ts_exit == 0 and StateManager.is_autonomous() else f"{COLOR_GREEN}✔ Tailscale Status: CONNECTED{COLOR_RESET}")
            
            # Parse IPs
            for line in ts_out.splitlines():
                parts = line.split()
                if not parts:
                    continue
                # Find laptop IP (the one with the hostname of active linux target)
                if "linux" in line or "nixos" in line:
                    laptop_ip = parts[0]
                # Find phone IP (matches android host)
                if "android" in line:
                    phone_ip = parts[0]
                    phone_hostname = parts[1]
            
            if laptop_ip:
                report.append(f"  - Laptop Tailscale IP: {COLOR_BOLD}{laptop_ip}{COLOR_RESET}")
            if phone_ip:
                report.append(f"  - Phone '{phone_hostname}' Tailscale IP: {COLOR_BOLD}{phone_ip}{COLOR_RESET}")
            else:
                report.append(f"  {COLOR_YELLOW}⚠ No Android/phone peer detected on Tailscale.{COLOR_RESET}")
        else:
            report.append(f"{COLOR_RED}✘ Tailscale Status: DISCONNECTED (Exit {ts_exit}){COLOR_RESET}")
            report.append("  - Please check your Tailscale client setup or restart it.")

        # ── Check 2: PhoneNotify Relay Server status ──
        server_running = False
        phones_connected = 0
        extensions_connected = 0
        
        try:
            # Call status API
            import httpx
            resp = httpx.get("http://localhost:8080/status", timeout=2.0)
            if resp.status_code == 200:
                server_running = True
                data = resp.json()
                conns = data.get("connections", {})
                phones_connected = conns.get("phones", 0)
                extensions_connected = conns.get("extensions", 0)
        except Exception:
            pass

        if server_running:
            report.append(f"{COLOR_GREEN}✔ PhoneNotify Server: ACTIVE (listening on port 8080){COLOR_RESET}")
            report.append(f"  - Connected Phones: {COLOR_BOLD}{phones_connected}{COLOR_RESET}")
            report.append(f"  - Connected Extensions: {COLOR_BOLD}{extensions_connected}{COLOR_RESET}")
        else:
            report.append(f"{COLOR_RED}✘ PhoneNotify Server: INACTIVE or UNREACHABLE (port 8080 is down){COLOR_RESET}")
            report.append("  - Try starting/restarting it: systemctl --user restart phone-notify.service")

        # ── Check 3: ADB status ──
        adb_exit, adb_out, adb_err = CommandExecutor.run_shell(["adb", "devices"])
        adb_connected_devices = []
        if adb_exit == 0:
            report.append(f"{COLOR_GREEN}✔ ADB Link: ACTIVE{COLOR_RESET}")
            for line in adb_out.splitlines():
                if "devices attached" in line or not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    adb_connected_devices.append(parts[0])
            
            if adb_connected_devices:
                for dev in adb_connected_devices:
                    report.append(f"  - Connected device: {COLOR_BOLD}{dev}{COLOR_RESET}")
            else:
                report.append("  - No devices currently connected over ADB.")
        else:
            report.append(f"{COLOR_YELLOW}⚠ ADB status check failed: adb command returned exit code {adb_exit}{COLOR_RESET}")

        # ── Check 4: Diagnostic analysis & advice ──
        report.append(f"\n{COLOR_CYAN}{COLOR_BOLD}=== DIAGNOSIS & RECOVERY ADVICE ==={COLOR_RESET}")
        
        has_issue = False
        
        # Scenario A: Phone is not connected to the server
        if server_running and phones_connected == 0:
            has_issue = True
            report.append(f"\n{COLOR_YELLOW}{COLOR_BOLD}[IP/Connection Mismatch Detected]{COLOR_RESET}")
            report.append("  The PhoneNotify server is active, but your Android app is not connected.")
            
            if phone_ip:
                # Phone exists on Tailscale, but not connected
                report.append(f"  1. Verify the app settings on your phone (galaxy-a13).")
                report.append(f"     It must point to the laptop's Tailscale IP: {COLOR_BOLD}ws://{laptop_ip if laptop_ip else '100.91.159.98'}:8080{COLOR_RESET}")
                
                # Check if connected over ADB
                adb_match = any(phone_ip in dev for dev in adb_connected_devices)
                if not adb_match:
                    report.append(f"  2. Establish ADB connection over Tailscale to sync or debug the device:")
                    report.append(f"     Run command: {COLOR_BOLD}adb connect {phone_ip}:5555{COLOR_RESET}")
            else:
                report.append("  1. Make sure Tailscale is enabled on both your phone and laptop.")
                report.append("  2. If on the same WiFi network without Tailscale, verify your phone connects to the laptop's local IP address.")

        # Scenario B: Extension is not connected to the server
        if server_running and extensions_connected == 0:
            has_issue = True
            report.append(f"\n{COLOR_YELLOW}{COLOR_BOLD}[Chromium Extension Disconnected]{COLOR_RESET}")
            report.append("  Your Chromium extension is not connected to the relay server.")
            report.append("  1. Click on the extension icon in Chromium to open the sidepanel.")
            report.append(f"  2. In Settings, confirm the WebSocket address is: {COLOR_BOLD}ws://localhost:8080{COLOR_RESET}")

        # Scenario C: Everything is perfect
        if not has_issue and server_running:
            report.append(f"\n{COLOR_GREEN}{COLOR_BOLD}✔ All systems green!{COLOR_RESET}")
            report.append("  Tailscale, ADB, PhoneNotify Relay, and your device connections are working perfectly!")

        report.append("\n============================================")
        return "\n".join(report)
