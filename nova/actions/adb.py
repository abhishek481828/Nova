import shutil
import time
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.executor import CommandExecutor
from nova.utils import print_info, print_error, print_warning, ask_confirmation

class AdbAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "adb_action"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "").strip().lower()
        target = params.get("target", "").strip()

        # Check if adb is installed
        if not shutil.which("adb"):
            return "Error: The 'adb' tool is not installed or not in your PATH. You can install it using: nova install android-tools"

        if operation == "devices":
            print_info("Checking connected ADB devices...")
            exit_code, stdout, stderr = CommandExecutor.run_shell(["adb", "devices"])
            if exit_code != 0:
                return (
                    f"Failed to list ADB devices. Error: {stderr.strip()}\n"
                    "Possible solution: Ensure ADB is installed and start the server using 'adb start-server'."
                )
            
            lines = stdout.strip().splitlines()
            devices_info = []
            for line in lines:
                if "devices attached" in line or not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    devices_info.append((parts[0], parts[1]))
            
            if not devices_info:
                summary = [
                    "ADB Devices List is empty.",
                    "\n❌ Status: BAD (No devices connected)",
                    "\nPossible Solutions:",
                    "  1. Connect your phone to your laptop using a USB cable.",
                    "  2. Make sure Developer Options and USB Debugging are enabled on your phone.",
                    "  3. If you want to connect wirelessly over network/Tailscale, run: 'nova adb connect 100.103.254.2:5555'"
                ]
                return "\n".join(summary)
            
            summary = ["ADB Devices List:"]
            good_connections = []
            issues = []
            
            for dev, status in devices_info:
                is_wireless = ":" in dev
                summary.append(f"  - {dev} ({'Wireless' if is_wireless else 'USB'}): {status.upper()}")
                
                if status == "device":
                    good_connections.append((dev, is_wireless))
                elif status == "unauthorized":
                    issues.append(
                        f"  ⚠️ Device '{dev}' is unauthorized.\n"
                        f"    -> Solution: Please unlock your phone and accept the 'Allow USB debugging?' prompt."
                    )
                elif status == "offline":
                    issues.append(
                        f"  ⚠️ Device '{dev}' is offline.\n"
                        f"    -> Solution: Re-connect the cable, or restart the ADB server: 'adb kill-server && adb start-server'."
                    )
                else:
                    issues.append(f"  ⚠️ Device '{dev}' has unexpected status: {status}.")

            if good_connections:
                summary.append("\n✅ Status: GOOD")
                for dev, is_wireless in good_connections:
                    if is_wireless:
                        summary.append(f"  - Wireless TCP/IP connection on '{dev}' is fully active and ready!")
                    else:
                        summary.append(f"  - USB connection on '{dev}' is active. If you want to switch to wireless, run: 'nova adb setup'.")
            
            if issues:
                summary.append("\n❌ Status: BAD (Some devices have connection issues)")
                summary.extend(issues)
                
            return "\n".join(summary)

        elif operation == "connect":
            if not target:
                target = input("Enter device IP address (e.g. 192.168.1.50:5555): ").strip()
                if not target:
                    return "Error: No target device IP provided."
            
            print_info(f"Connecting to ADB target: {target}...")
            exit_code, stdout, stderr = CommandExecutor.run_shell(["adb", "connect", target])
            if exit_code == 0:
                return f"ADB Connect Output:\n{stdout.strip()}"
            else:
                return f"Failed to connect to target. Error: {stderr}"

        elif operation == "disconnect":
            print_info(f"Disconnecting ADB target {target if target else 'all devices'}...")
            cmd = ["adb", "disconnect"]
            if target:
                cmd.append(target)
                
            exit_code, stdout, stderr = CommandExecutor.run_shell(cmd)
            if exit_code == 0:
                return f"ADB Disconnect Output:\n{stdout.strip()}"
            else:
                return f"Failed to disconnect. Error: {stderr}"

        elif operation == "setup" or operation == "setup_tcpip":
            print_info("Preparing ADB TCP/IP wireless setup...")
            
            # Step 1: Put connected USB device into TCP/IP mode on port 5555
            print_info("Putting USB-connected device into TCP/IP mode (port 5555)...")
            exit_code, stdout, stderr = CommandExecutor.run_shell(["adb", "tcpip", "5555"])
            if exit_code != 0:
                return (
                    f"Failed to put device in TCP/IP mode. Error: {stderr.strip()}\n"
                    "Make sure your phone is plugged in via USB and USB Debugging is enabled!"
                )
                
            # Step 2: Determine target IP (defaulting to Tailscale phone IP)
            target_ip = target
            if not target_ip:
                # Attempt to auto-detect phone's Tailscale IP
                ts_exit, ts_out, ts_err = CommandExecutor.run_shell(["tailscale", "status"])
                if ts_exit == 0:
                    for line in ts_out.splitlines():
                        if "android" in line:
                            target_ip = line.split()[0]
                            break
            
            if not target_ip:
                target_ip = input("Enter your phone's IP address (e.g. 100.103.254.2): ").strip()
                
            if not target_ip:
                return "TCP/IP port 5555 enabled. Please run: nova adb connect <phone_ip>"
                
            if ":" not in target_ip:
                connect_target = f"{target_ip}:5555"
            else:
                connect_target = target_ip
                
            print_info(f"Connecting to wireless target: {connect_target}...")
            # Wait 2 seconds for adbd restart on the phone
            import time
            time.sleep(2)
            
            c_exit, c_out, c_err = CommandExecutor.run_shell(["adb", "connect", connect_target])
            if c_exit == 0:
                return (
                    f"Successfully configured wireless debugging!\n"
                    f"ADB Output: {c_out.strip()}\n"
                    f"You can now unplug the USB cable from your phone."
                )
            else:
                return f"TCP/IP mode set, but wireless connection failed: {c_err.strip()}"

        elif operation == "mirror":
            return start_mirroring()

        else:
            return f"Error: Unsupported ADB operation '{operation}'. Supported: devices, connect, disconnect, setup, mirror."

def start_mirroring() -> str:
    phone_ip = "100.103.254.2"
    phone_port = "5555"
    target = f"{phone_ip}:{phone_port}"
    
    print_info("Starting phone screen mirroring diagnostics...")
    
    # 1. Check if adb is installed
    if not shutil.which("adb"):
        print_warning("ADB (android-tools) is not installed. Attempting to install it...")
        if ask_confirmation("Would you like Nova to install Android SDK platform tools (adb)?"):
            print_info("Installing android-tools...")
            exit_code, out, err = CommandExecutor.run_shell(
                ["nix", "profile", "install", "nixpkgs#android-tools"],
                require_confirmation=True,
                confirm_message="Install android-tools package"
            )
            if exit_code != 0:
                return f"Failed to install android-tools: {err.strip()}"
            print_info("android-tools installed successfully!")
        else:
            return "Error: ADB is required for screen mirroring. Please install it."

    # 2. Check if scrcpy is installed
    if not shutil.which("scrcpy"):
        print_warning("scrcpy is not installed. Attempting to install it...")
        if ask_confirmation("Would you like Nova to install scrcpy for screen mirroring?"):
            print_info("Installing scrcpy...")
            exit_code, out, err = CommandExecutor.run_shell(
                ["nix", "profile", "install", "nixpkgs#scrcpy"],
                require_confirmation=True,
                confirm_message="Install scrcpy package"
            )
            if exit_code != 0:
                return f"Failed to install scrcpy: {err.strip()}"
            print_info("scrcpy installed successfully!")
        else:
            return "Error: scrcpy is required for screen mirroring. Please install it."

    # 3. Check current ADB devices
    exit_code, stdout, stderr = CommandExecutor.run_shell(["adb", "devices"])
    if exit_code != 0:
        print_warning("ADB server is not responding. Attempting to restart ADB server...")
        CommandExecutor.run_shell(["adb", "kill-server"])
        CommandExecutor.run_shell(["adb", "start-server"])
        exit_code, stdout, stderr = CommandExecutor.run_shell(["adb", "devices"])
        if exit_code != 0:
            return "Error: ADB server is not working. Try running 'adb start-server' manually."

    # Parse devices
    devices = {}
    for line in stdout.splitlines():
        if "devices attached" in line or not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices[parts[0]] = parts[1]

    # Helper function to check if target device is connected
    def is_target_connected() -> bool:
        return target in devices and devices[target] == "device"

    # If already connected wirelessly, skip connection setup
    if is_target_connected():
        print_info("Phone is already connected wirelessly over ADB.")
    else:
        # Try to connect wirelessly
        print_info(f"Connecting to wireless target: {target}...")
        CommandExecutor.run_shell(["adb", "connect", target])
        
        # Re-fetch devices
        exit_code, stdout, stderr = CommandExecutor.run_shell(["adb", "devices"])
        devices = {}
        for line in stdout.splitlines():
            if "devices attached" in line or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                devices[parts[0]] = parts[1]
                
        if is_target_connected():
            print_info("Successfully connected to phone wirelessly!")
        else:
            # Wireless connection failed, let's diagnose why
            print_warning("Wireless ADB connection failed. Analyzing the problem...")
            
            # Diagnose A: Is it unauthorized or offline?
            if target in devices:
                status = devices[target]
                if status == "unauthorized":
                    return (
                        "Problem: Phone is connected over the network, but unauthorized.\n"
                        "How to solve: Please check your phone screen for an 'Allow USB debugging?' prompt and select 'Allow' or 'Always allow'."
                    )
                elif status == "offline":
                    print_info("Device is offline. Re-connecting ADB...")
                    CommandExecutor.run_shell(["adb", "disconnect", target])
                    time.sleep(1)
                    CommandExecutor.run_shell(["adb", "connect", target])
            
            # Diagnose B: USB connection check
            usb_devices = [dev for dev, status in devices.items() if ":" not in dev and status == "device"]
            
            if usb_devices:
                usb_dev = usb_devices[0]
                print_info(f"Detected USB-connected device: {usb_dev}")
                print_info("Attempting to automatically transition to wireless debugging (TCP/IP mode)...")
                
                # Set TCP/IP port 5555
                t_code, t_out, t_err = CommandExecutor.run_shell(["adb", "-s", usb_dev, "tcpip", "5555"])
                if t_code == 0:
                    print_info("Successfully put phone into TCP/IP mode on port 5555.")
                    print_info("Waiting 3 seconds for device to re-initialize adbd...")
                    time.sleep(3)
                    
                    # Connect wirelessly
                    CommandExecutor.run_shell(["adb", "connect", target])
                    
                    # Re-fetch devices
                    _, stdout, _ = CommandExecutor.run_shell(["adb", "devices"])
                    devices = {}
                    for line in stdout.splitlines():
                        if "devices attached" in line or not line.strip():
                            continue
                        parts = line.split()
                        if len(parts) >= 2:
                            devices[parts[0]] = parts[1]
                    
                    if is_target_connected():
                        print_info("Successfully switched to wireless debugging and connected!")
                    else:
                        print_warning("Wireless connection failed after setting TCP/IP port. Testing network reachability...")
                else:
                    print_warning(f"Failed to put device into TCP/IP mode: {t_err.strip()}")

            # Diagnose C: Tailscale Reachability Check
            if not is_target_connected():
                print_info(f"Pinging phone IP {phone_ip}...")
                p_code, _, _ = CommandExecutor.run_shell(["ping", "-c", "1", "-W", "1", phone_ip])
                
                if p_code != 0:
                    # Ping failed: Network issue
                    # Check laptop Tailscale status
                    ts_code, ts_out, ts_err = CommandExecutor.run_shell(["tailscale", "status"])
                    if ts_code != 0:
                        return (
                            "Problem: Tailscale is not running on your laptop.\n"
                            "How to solve: Start the Tailscale service on your laptop by running:\n"
                            "  sudo systemctl start tailscaled"
                        )
                    else:
                        # Check if phone IP is in the tailscale status
                        phone_in_ts = False
                        for line in ts_out.splitlines():
                            if phone_ip in line:
                                phone_in_ts = True
                                break
                        
                        if not phone_in_ts:
                            return (
                                f"Problem: The phone IP '{phone_ip}' was not found in your Tailscale peer list.\n"
                                "How to solve:\n"
                                "  1. Verify Tailscale is active and logged in on both the laptop and phone.\n"
                                "  2. Ensure the phone is signed in to the same Tailscale account."
                            )
                        else:
                            return (
                                f"Problem: Phone ({phone_ip}) is in your Tailscale list, but it is not reachable (ping timed out).\n"
                                "How to solve:\n"
                                "  1. Make sure your phone has internet connectivity and WiFi is turned on.\n"
                                "  2. Verify that the Tailscale app is active (running/connected) on the phone."
                            )
                else:
                    # Ping succeeded but port 5555 is closed
                    return (
                        f"Problem: The phone ({phone_ip}) is reachable on the network, but port 5555 is not open (wireless debugging is disabled).\n"
                        "How to solve:\n"
                        "  1. Plug your phone into your laptop via USB cable.\n"
                        f"  2. Run 'nova adb setup' so Nova can configure wireless debugging for you.\\n"
                        f"  3. Once set up, you can unplug the USB cable and run 'nova mirror phone' wirelessly."
                    )

    # 4. Launch scrcpy in the background
    print_info("Launching phone screen mirroring via scrcpy...")
    exit_code, msg = CommandExecutor.run_background("scrcpy", shell=True)
    if exit_code == 0:
        return "Successfully launched phone screen mirroring (scrcpy) in the background!"
    else:
        return f"Failed to start scrcpy. Error: {msg}"
