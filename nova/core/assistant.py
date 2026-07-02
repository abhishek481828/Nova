import sys
import os
import glob
import socket
import signal

_sigterm_triggered = False

def sigterm_handler(signum, frame):
    global _sigterm_triggered
    if _sigterm_triggered:
        return
    _sigterm_triggered = True
    raise KeyboardInterrupt

signal.signal(signal.SIGTERM, sigterm_handler)

# Auto-detect and include the project root and local .venv virtualenv site-packages
try:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    venv_pattern = os.path.join(project_root, ".venv", "lib", "python*", "site-packages")
    venv_dirs = glob.glob(venv_pattern)
    for venv_dir in venv_dirs:
        while venv_dir in sys.path:
            try:
                sys.path.remove(venv_dir)
            except ValueError:
                break
        sys.path.append(venv_dir)
except Exception:
    pass

from nova.core.state import StateManager
from nova.utils import (
    print_success,
    print_info,
    print_error,
    print_warning,
)

# Re-export client, daemon and cli submodules for backward compatibility
from nova.core.cli import run_cli_repl
from nova.core.daemon import run_daemon
from nova.core.client import run_client

def get_greeting() -> str:
    from datetime import datetime
    
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

def main() -> None:
    args = sys.argv[1:]
    
    # Check for direct service commands
    if args:
        cmd = args[0].lower().strip()
        if cmd == "start":
            import subprocess
            subprocess.run(["systemctl", "--user", "start", "nova.service"])
            print_success("Nova service started.")
            return
        elif cmd == "stop":
            import subprocess
            subprocess.run(["systemctl", "--user", "stop", "nova.service"])
            print_success("Nova service stopped.")
            return
        elif cmd == "restart":
            import subprocess
            subprocess.run(["systemctl", "--user", "restart", "nova.service"])
            print_success("Nova service restarted.")
            return
        elif cmd == "status":
            # Check if daemon is running by attempting to connect
            daemon_running = False
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", 11435))
                daemon_running = True
                s.close()
            except Exception:
                pass

            if daemon_running:
                run_client("STATUS")
            else:
                import subprocess
                res = subprocess.run(["systemctl", "--user", "is-active", "nova.service"], capture_output=True, text=True)
                active_status = res.stdout.strip()
                print(f"○ Nova Assistant Service")
                print(f"   Status:             Stopped ({active_status})")
                print(f"   Background Service: Inactive")
            return

    # Check for direct voice subsystem commands
    if args:
        cmd = args[0].lower().strip()
        if cmd == "voice-setup":
            from nova.voice.speaker import run_speaker_enrollment_wizard as voice_setup_main
            voice_setup_main()
            return
        elif cmd == "voice-reset":
            from nova.voice.speaker import run_speaker_reset_wizard as voice_reset_main
            voice_reset_main()
            return
        elif cmd == "voice-test":
            from nova.voice.pipeline import run_voice_self_test as voice_test_main
            voice_test_main()
            return
            
    # Check if daemon is running by attempting to connect
    daemon_running = False
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", 11435))
        daemon_running = True
        s.close()
    except Exception:
        pass

    # Run interactive/voice mode directly in the foreground if stdin is a TTY and either
    # no arguments are passed or "--text" is specified.
    is_interactive = sys.stdin.isatty() and (not args or "--text" in args)

    if not is_interactive and daemon_running and "--daemon" not in args:
        if not args:
            run_client("TOGGLE_VOICE")
            return
        else:
            query = " ".join(args)
            run_client(query)
            return

    if not is_interactive and not daemon_running and "--daemon" not in args:
        if not args:
            # Launcher mode / shortcut: start daemon silently in the background
            import subprocess
            import time
            subprocess.run(["systemctl", "--user", "start", "nova.service"])
            for _ in range(10):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                try:
                    s.connect(("127.0.0.1", 11435))
                    s.close()
                    daemon_running = True
                    break
                except Exception:
                    time.sleep(0.5)
            if daemon_running:
                run_client("TOGGLE_VOICE")
            else:
                print_error("Failed to start Nova daemon.")
            return
        else:
            # Client mode query: start daemon, wait, and run client query
            import subprocess
            import time
            subprocess.run(["systemctl", "--user", "start", "nova.service"])
            print_info("Starting Nova daemon...")
            for _ in range(10):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                try:
                    s.connect(("127.0.0.1", 11435))
                    s.close()
                    daemon_running = True
                    break
                except Exception:
                    time.sleep(0.5)
            if daemon_running:
                query = " ".join(args)
                run_client(query)
            else:
                print_error("Failed to start Nova daemon.")
            return

    # Daemon Mode
    if "--daemon" in args:
        run_daemon()
        return
        
    # Interactive REPL CLI Mode
    run_cli_repl(args)

if __name__ == "__main__":
    main()
