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

from nova.utils import (
    print_info,
    print_error,
)

# Re-export client, daemon and cli submodules for backward compatibility
from nova.core.cli import run_cli_repl
from nova.core.daemon import run_daemon
from nova.core.client import run_client

# Import helpers from orchestrator
from nova.core.orchestrator import (
    get_greeting,
    is_daemon_running,
    handle_service_command,
    start_daemon_background,
)

def main() -> None:
    args = sys.argv[1:]
    
    # Check for direct service commands
    if args:
        cmd = args[0].lower().strip()
        if handle_service_command(cmd):
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
        elif cmd == "wake-diag":
            import nova.voice.wizards.diag_wake
            return
            
    # Check if daemon is running by attempting to connect
    daemon_running = is_daemon_running()

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
            if start_daemon_background():
                run_client("TOGGLE_VOICE")
            else:
                print_error("Failed to start Nova daemon.")
            return
        else:
            # Client mode query: start daemon, wait, and run client query
            print_info("Starting Nova daemon...")
            if start_daemon_background():
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
