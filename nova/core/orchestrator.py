import os
import time
import socket
import subprocess
from datetime import datetime
from nova.core.state import StateManager
from nova.core.client import run_client
from nova.utils import print_success, print_info, print_error

def get_greeting() -> str:
    # Reload state to get latest profile updates
    StateManager.load_state()
    user_profile = StateManager.get_user_profile()
    name = "Boss"
    if user_profile and isinstance(user_profile, dict) and user_profile.get("name"):
        name = user_profile.get("name")
        
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return f"Good morning, {name}!"
    elif 12 <= hour < 17:
        return f"Good afternoon, {name}!"
    elif 17 <= hour < 22:
        return f"Good evening, {name}!"
    else:
        return f"Hello, {name}!"

def is_daemon_running() -> bool:
    daemon_running = False
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", 11435))
        daemon_running = True
        s.close()
    except Exception:
        pass
    return daemon_running

def handle_service_command(cmd: str) -> bool:
    cmd_clean = cmd.lower().strip()
    if cmd_clean == "start":
        subprocess.run(["systemctl", "--user", "start", "nova.service"])
        print_success("Nova service started.")
        return True
    elif cmd_clean == "stop":
        subprocess.run(["systemctl", "--user", "stop", "nova.service"])
        print_success("Nova service stopped.")
        return True
    elif cmd_clean == "restart":
        subprocess.run(["systemctl", "--user", "restart", "nova.service"])
        print_success("Nova service restarted.")
        return True
    elif cmd_clean == "status":
        if is_daemon_running():
            run_client("STATUS")
        else:
            res = subprocess.run(["systemctl", "--user", "is-active", "nova.service"], capture_output=True, text=True)
            active_status = res.stdout.strip()
            print("○ Nova Assistant Service")
            print(f"   Status:             Stopped ({active_status})")
            print("   Background Service: Inactive")
        return True
    return False

def start_daemon_background() -> bool:
    subprocess.run(["systemctl", "--user", "start", "nova.service"])
    for _ in range(10):
        if is_daemon_running():
            return True
        time.sleep(0.5)
    return False
