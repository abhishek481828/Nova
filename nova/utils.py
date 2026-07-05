import sys
from typing import Optional

# ANSI Colors
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_BLUE = "\033[94m"
COLOR_CYAN = "\033[96m"

_socket_conn = None
_capture_callback = None
_original_stdout = sys.stdout

class SocketStdout:
    def write(self, data: str) -> int:
        _write(data)
        return len(data)
    def flush(self) -> None:
        pass

def set_socket_conn(conn) -> None:
    global _socket_conn
    _socket_conn = conn
    if conn is not None:
        sys.stdout = SocketStdout()
    else:
        sys.stdout = _original_stdout

def set_capture_callback(callback) -> None:
    global _capture_callback
    _capture_callback = callback

def _write(message: str, is_error: bool = False) -> None:
    global _socket_conn, _capture_callback
    if _capture_callback:
        try:
            _capture_callback(message)
        except Exception:
            pass

    # Mirror all console writes to the dashboard
    try:
        from nova.dashboard.event_bus import emit
        emit("console_output", module="core", status="success", metadata={"message": message, "is_error": is_error})
    except Exception:
        pass

    if _socket_conn:
        try:
            _socket_conn.sendall(message.encode("utf-8"))
        except Exception:
            pass
    else:
        if is_error:
            sys.stderr.write(message)
            sys.stderr.flush()
        else:
            _original_stdout.write(message)
            _original_stdout.flush()

def print_success(message: str) -> None:
    _write(f"{COLOR_GREEN}{COLOR_BOLD}✔{COLOR_RESET} {message}\n")

def print_info(message: str) -> None:
    _write(f"{COLOR_BLUE}{COLOR_BOLD}ℹ{COLOR_RESET} {message}\n")

def print_warning(message: str) -> None:
    _write(f"{COLOR_YELLOW}{COLOR_BOLD}⚠{COLOR_RESET} {message}\n")

def print_error(message: str) -> None:
    _write(f"{COLOR_RED}{COLOR_BOLD}✘{COLOR_RESET} {message}\n", is_error=True)

def print_banner() -> None:
    from nova.version import __version__
    banner = f"""
{COLOR_CYAN}{COLOR_BOLD}   __                         
  / /  ___ _  ______  _______ 
 / _ \\/ _ `/ / __/\\ \\/ (_-<_-<
/_//_/\\_,_/_/_/    \\_/_/___/___/
{COLOR_RESET}
Nova AI Assistant
Version: {__version__}
    """
    _write(banner)

def ask_confirmation(prompt_msg: str = "Proceed?") -> bool:
    """Prompt the user with a Proceed (y/n) check."""
    global _socket_conn
    import threading
    # Auto-approve instantly for remote Telegram commands
    if threading.current_thread().name == "telegram_polling_thread":
        return True
        
    prompt_str = f"{COLOR_YELLOW}{COLOR_BOLD}{prompt_msg} (y/n): {COLOR_RESET}"
    try:
        while True:
            if _socket_conn:
                _socket_conn.sendall(prompt_str.encode("utf-8"))
                choice = _socket_conn.recv(1024).decode("utf-8").lower().strip()
                if not choice:
                    return False
            else:
                if not sys.stdin.isatty():
                    from nova.core.state import StateManager
                    # Auto-approve if system is in autonomous mode
                    if StateManager.is_autonomous():
                        return True
                    return False
                choice = input(prompt_str).lower().strip()
                
            if choice in ("y", "yes"):
                return True
            if choice in ("n", "no"):
                return False
                
            msg = "Please enter 'y' or 'n'.\n"
            if _socket_conn:
                _socket_conn.sendall(msg.encode("utf-8"))
            else:
                print(msg, end="")
    except (KeyboardInterrupt, EOFError):
        if not _socket_conn:
            print()  # print newline
        return False

def resolve_chromium_bin() -> Optional[str]:
    import os
    import shutil

    # 1. Check env variables
    for env_var in ["CHROMIUM_BIN"]:
        val = os.environ.get(env_var)
        if val and os.path.exists(val):
            return os.path.realpath(val)

    # 2. Check shutil.which
    p = shutil.which("chromium")
    if p:
        return os.path.realpath(p)

    # 3. Check known NixOS path
    known_paths = [
        "/run/current-system/sw/bin/chromium"
    ]
    for p in known_paths:
        if os.path.exists(p):
            return os.path.realpath(p)

    return None


