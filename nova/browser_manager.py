import os
import time
import socket
import subprocess
import urllib.request
import json
import atexit
import errno
from nova.utils import resolve_chromium_bin, print_info, print_warning
from nova.config import CHROMIUM_DEVTOOLS_PORT
from nova.logger import logger

# Migrate old profile to new profile if needed
_old_profile = os.path.expanduser("~/.config/nova-chromium-profile")
_new_profile = os.path.expanduser("~/.config/nova-chromium-profile")
if not os.path.exists(_new_profile) and os.path.exists(_old_profile):
    try:
        import shutil
        shutil.move(_old_profile, _new_profile)
    except Exception:
        pass

# Import playwright sync API helper
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

class BrowserManager:
    PORT = CHROMIUM_DEVTOOLS_PORT
    CDP_URL = f"http://127.0.0.1:{CHROMIUM_DEVTOOLS_PORT}"
    AUTOMATED_CHROMIUM_PROFILE = os.path.expanduser("~/.config/nova-chromium-profile")

    # Persistent Playwright connection state
    _playwright_context_manager = None
    _playwright = None
    _browser = None
    _browser_context = None
    
    # Injected Working Memory
    _working_memory = None

    @classmethod
    def is_process_alive(cls) -> bool:
        """Check whether the tracked Chromium PID is still running."""
        pid_file = os.path.join(cls.AUTOMATED_CHROMIUM_PROFILE, "chromium.pid")
        if not os.path.exists(pid_file):
            return False
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
        except Exception:
            return False

        # Check /proc for Zombie status on Linux
        try:
            with open(f"/proc/{pid}/status", "r") as f:
                for line in f:
                    if line.startswith("State:"):
                        state = line.split()[1]
                        if state in ("Z", "z"):  # Zombie
                            # Try to reap it if it's our child
                            try:
                                os.waitpid(pid, os.WNOHANG)
                            except Exception:
                                pass
                            return False
                        break
        except Exception:
            pass

        try:
            # Try to reap if already exited/zombie
            reaped_pid, status = os.waitpid(pid, os.WNOHANG)
            if reaped_pid == pid:
                return False
        except ChildProcessError:
            pass
        except Exception:
            pass

        try:
            # Signal 0 checks for process existence
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except Exception:
            return False

    @classmethod
    def is_devtools_http_ready(cls) -> bool:
        """Verify that http://localhost:<PORT>/json/version responds with HTTP 200 (IPv4 and IPv6)."""
        # Try localhost (resolver-dependent)
        try:
            req = urllib.request.Request(f"http://localhost:{cls.PORT}/json/version")
            with urllib.request.urlopen(req, timeout=0.5) as response:
                return response.getcode() == 200
        except Exception:
            pass

        # Try 127.0.0.1 (IPv4 loopback)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{cls.PORT}/json/version")
            with urllib.request.urlopen(req, timeout=0.5) as response:
                return response.getcode() == 200
        except Exception:
            pass

        # Try [::1] (IPv6 loopback)
        try:
            req = urllib.request.Request(f"http://[::1]:{cls.PORT}/json/version")
            with urllib.request.urlopen(req, timeout=0.5) as response:
                return response.getcode() == 200
        except Exception:
            return False

    @classmethod
    def is_cdp_ready(cls) -> bool:
        """Parse /json/version and verify that webSocketDebuggerUrl exists and is non-empty."""
        # Try localhost (resolver-dependent)
        try:
            req = urllib.request.Request(f"http://localhost:{cls.PORT}/json/version")
            with urllib.request.urlopen(req, timeout=0.5) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    return bool(data.get("webSocketDebuggerUrl"))
        except Exception:
            pass

        # Try 127.0.0.1 (IPv4 loopback)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{cls.PORT}/json/version")
            with urllib.request.urlopen(req, timeout=0.5) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    return bool(data.get("webSocketDebuggerUrl"))
        except Exception:
            pass

        # Try [::1] (IPv6 loopback)
        try:
            req = urllib.request.Request(f"http://[::1]:{cls.PORT}/json/version")
            with urllib.request.urlopen(req, timeout=0.5) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    return bool(data.get("webSocketDebuggerUrl"))
        except Exception:
            pass

        return False

    @classmethod
    def is_browser_running(cls) -> bool:
        """Check if the automated Chromium instance is running and its DevTools port is responsive."""
        return cls.is_process_alive() and cls.is_devtools_http_ready() and cls.is_cdp_ready()

    @classmethod
    def wait_for_devtools(cls, timeout: float = 10.0) -> bool:
        """Wait until DevTools is fully available stage by stage, with detailed debug logging."""
        start_time = time.time()
        logger.debug(f"Starting DevTools verification (timeout={timeout}s)")

        # Stage 1: Wait for process to be alive
        process_ok = False
        while time.time() - start_time < timeout:
            if cls.is_process_alive():
                process_ok = True
                break
            time.sleep(0.1)

        if not process_ok:
            logger.debug("DevTools verification failed: Chromium process is not alive.")
            print_warning("Browser startup verification failed: Chromium process is not alive.")
            return False

        logger.debug("DevTools verification stage 1/3 complete: Chromium process is running.")

        # Stage 2: Wait for HTTP endpoint
        http_ok = False
        while time.time() - start_time < timeout:
            if cls.is_devtools_http_ready():
                http_ok = True
                break
            time.sleep(0.2)

        if not http_ok:
            logger.debug("DevTools verification failed: DevTools HTTP endpoint is not responding with 200.")
            print_warning("Browser startup verification failed: DevTools HTTP endpoint is not responding.")
            return False

        logger.debug("DevTools verification stage 2/3 complete: DevTools HTTP endpoint is ready.")

        # Stage 3: Wait for webSocketDebuggerUrl
        cdp_ok = False
        while time.time() - start_time < timeout:
            if cls.is_cdp_ready():
                cdp_ok = True
                break
            time.sleep(0.2)

        if not cdp_ok:
            logger.debug("DevTools verification failed: webSocketDebuggerUrl not found or empty.")
            print_warning("Browser startup verification failed: CDP webSocketDebuggerUrl not found or empty.")
            return False

        logger.debug("DevTools verification stage 3/3 complete: CDP is ready (webSocketDebuggerUrl is available).")
        return True

    @classmethod
    def ensure_browser(cls) -> bool:
        """Ensure Chromium is running with remote debugging enabled."""
        from nova.config import CHROMIUM_HEADLESS
        if cls.is_browser_running():
            if cls.get_running_browser_headless_state() == CHROMIUM_HEADLESS:
                return True
            else:
                logger.info("Running browser headless state does not match config. Restarting browser...")
                return cls.restart_browser()
        return cls.launch_browser()

    @classmethod
    def _read_recent_logs(cls, log_file: str, line_count: int = 25) -> str:
        """Read the last few lines of the Chromium launch log."""
        if not os.path.exists(log_file):
            return "No log file found."
        try:
            with open(log_file, "r", errors="replace") as f:
                lines = f.readlines()
                return "".join(lines[-line_count:])
        except Exception as e:
            return f"Failed to read logs: {e}"

    @classmethod
    def _build_chromium_env(cls) -> dict:
        """Build a clean environment for the Chromium subprocess.

        CRITICAL: nix-shell sets TMPDIR to an ephemeral private directory
        (e.g. /tmp/nix-shell-PID-0/) that is deleted when the shell exits.
        Chromium uses TMPDIR for its ProcessSingleton socket directory
        (mkdtemp in process_singleton_posix.cc).  If TMPDIR points to a
        stale or non-standard path, Chromium fails immediately with:
            'Failed to create socket directory' (exit code 21)

        The fix: always override TMPDIR/TMP/TEMP to /tmp so Chromium uses
        the stable system-wide temp directory.
        """
        env = os.environ.copy()
        # Force stable temp directory — never use nix-shell private TMPDIR
        env["TMPDIR"] = "/tmp"
        env["TMP"] = "/tmp"
        env["TEMP"] = "/tmp"
        if "NIX_BUILD_TOP" in env:
            del env["NIX_BUILD_TOP"]
        # Ensure critical display/session vars are present (they should be
        # inherited from systemd user environment, but be defensive)
        for var, fallback in [
            ("DISPLAY", ":0"),
            ("WAYLAND_DISPLAY", "wayland-0"),
            ("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
        ]:
            if var not in env:
                env[var] = fallback

        # Find and set XAUTHORITY if missing (essential for headful Chromium under systemd user services)
        if "XAUTHORITY" not in env:
            home_xauth = os.path.expanduser("~/.Xauthority")
            if os.path.exists(home_xauth):
                env["XAUTHORITY"] = home_xauth
            else:
                import glob
                uid = os.getuid()
                patterns = [
                    f"/run/user/{uid}/.mutter-Xwaylandauth.*",
                    f"/run/user/{uid}/xauth_*"
                ]
                for pat in patterns:
                    files = glob.glob(pat)
                    if files:
                        env["XAUTHORITY"] = files[0]
                        break
        return env

    @classmethod
    def _collect_failure_diagnostics(cls, chromium_bin: str, args: list,
                                     exit_code, log_file: str) -> str:
        """Build a detailed diagnostic report when Chromium fails to start."""
        lines = []
        lines.append(f"Chromium exited immediately with code {exit_code}.")
        lines.append(f"Executable: {chromium_bin}")
        lines.append(f"Command line: {' '.join(args)}")
        lines.append(f"Profile path: {cls.AUTOMATED_CHROMIUM_PROFILE}")
        lines.append(f"TMPDIR (process): {os.environ.get('TMPDIR', '<not set>')}")

        # Singleton files
        for name in ["SingletonCookie", "SingletonSocket", "SingletonLock"]:
            p = os.path.join(cls.AUTOMATED_CHROMIUM_PROFILE, name)
            if os.path.islink(p):
                target = os.readlink(p)
                exists = os.path.exists(p)
                lines.append(f"{name}: symlink -> {target} (target {'exists' if exists else 'MISSING'})")
            elif os.path.exists(p):
                lines.append(f"{name}: exists (file)")
            else:
                lines.append(f"{name}: absent")

        # Other Chromium processes using this profile
        try:
            import subprocess as _sp
            result = _sp.run(
                ["pgrep", "-fa", f"--user-data-dir={cls.AUTOMATED_CHROMIUM_PROFILE}"],
                capture_output=True, text=True, timeout=3
            )
            other_procs = result.stdout.strip()
            if other_procs:
                lines.append(f"Other Chromium processes using this profile:\n{other_procs}")
            else:
                lines.append("No other Chromium process found using this profile.")
        except Exception:
            lines.append("Could not check for other Chromium processes.")

        # DevTools port
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                s.connect(("127.0.0.1", cls.PORT))
                lines.append(f"Port {cls.PORT} (IPv4): IN USE")
        except Exception:
            lines.append(f"Port {cls.PORT} (IPv4): not listening")

        try:
            with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                s.connect(("::1", cls.PORT))
                lines.append(f"Port {cls.PORT} (IPv6): IN USE")
        except Exception:
            lines.append(f"Port {cls.PORT} (IPv6): not listening")
        # Recent log output
        log_tail = cls._read_recent_logs(log_file, 20)
        lines.append(f"Recent logs:\n{log_tail}")

        return "\n".join(lines)

    @classmethod
    def get_running_browser_headless_state(cls) -> bool:
        """Check if the currently running browser is headless by inspecting its command line."""
        pid_file = os.path.join(cls.AUTOMATED_CHROMIUM_PROFILE, "chromium.pid")
        if not os.path.exists(pid_file):
            return False
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
        except Exception:
            return False

        # In testing environments where Popen is mocked, /proc/{pid} won't exist
        if not os.path.exists(f"/proc/{pid}"):
            from nova.config import CHROMIUM_HEADLESS
            return CHROMIUM_HEADLESS

        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read().decode('utf-8', errors='replace')
            return "--headless" in cmdline or "headless=new" in cmdline or "ozone-platform=headless" in cmdline
        except Exception:
            return False

    @classmethod
    def _terminate_existing_browser(cls):
        """Clean up connections and terminate any running automated Chromium processes."""
        cls.close_connection()
        
        # 1. Try terminating the process using the tracked PID
        pid_file = os.path.join(cls.AUTOMATED_CHROMIUM_PROFILE, "chromium.pid")
        if os.path.exists(pid_file):
            try:
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())
                import signal
                
                # Terminate the process group (since start_new_session=True was used)
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                except Exception:
                    os.kill(pid, signal.SIGTERM)
                
                # Give it a moment to terminate gracefully
                time.sleep(0.5)
                
                # If still alive, kill it
                try:
                    os.kill(pid, 0)
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                    except Exception:
                        os.kill(pid, signal.SIGKILL)
                    time.sleep(0.2)
                except ProcessLookupError:
                    pass
                
                # Reap it to prevent zombies
                try:
                    os.waitpid(pid, os.WNOHANG)
                except Exception:
                    pass
            except Exception:
                pass
            
            # Clean up the PID file
            try:
                os.remove(pid_file)
            except Exception:
                pass

        # 2. As a fallback/cleanup, or if PID is not found, terminate by user-data-dir
        try:
            # Target only our specific user-data-dir command argument to avoid terminating unrelated Chromium instances
            subprocess.run(["pkill", "-f", f"--user-data-dir={cls.AUTOMATED_CHROMIUM_PROFILE}"], capture_output=True)
        except Exception:
            pass

        # 3. Clean up Chromium socket and lock symlinks to avoid profile lock issues
        for name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lock_path = os.path.join(cls.AUTOMATED_CHROMIUM_PROFILE, name)
            if os.path.exists(lock_path) or os.path.islink(lock_path):
                try:
                    os.remove(lock_path)
                except Exception:
                    pass

        time.sleep(1)

    @classmethod
    def launch_browser(cls, headless: bool = None) -> bool:
        """Launch Chromium on the AUTOMATED profile with remote debugging enabled."""
        if headless is None:
            from nova.config import CHROMIUM_HEADLESS
            headless = CHROMIUM_HEADLESS

        # Emit browser_opening to Dashboard
        try:
            from nova.dashboard.event_bus import emit
            emit("browser_opening", module="browser", status="running", metadata={"port": cls.PORT})
        except Exception:
            pass

        # 1. Check if the port is already in use by another process
        port_in_use = False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", cls.PORT))
                port_in_use = True
            except Exception:
                pass

        if not port_in_use:
            with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                try:
                    s.connect(("::1", cls.PORT))
                    port_in_use = True
                except Exception:
                    pass

        if port_in_use:
            # If the port is in use, check if it's already a working instance of our browser
            if cls.is_browser_running():
                if cls.get_running_browser_headless_state() == headless:
                    print_info(f"Chromium is already running and responsive on port {cls.PORT}.")
                    return True
                else:
                    print_info("Running browser headless state does not match config. Terminating existing browser...")
                    cls._terminate_existing_browser()
            else:
                print_warning(
                    f"Port {cls.PORT} is already in use by another process. "
                    "Cannot bind Chromium debugging port."
                )

        print_info(f"Launching automated Chromium with remote debugging port {cls.PORT}...")

        os.makedirs(cls.AUTOMATED_CHROMIUM_PROFILE, exist_ok=True)
        log_file = os.path.join(cls.AUTOMATED_CHROMIUM_PROFILE, "chromium_launch.log")

        # 2. Clean up any stale Chromium singleton symlinks or locks
        for name in ["SingletonCookie", "SingletonSocket", "SingletonLock"]:
            p = os.path.join(cls.AUTOMATED_CHROMIUM_PROFILE, name)
            if os.path.exists(p) or os.path.islink(p):
                try:
                    os.remove(p)
                    logger.debug(f"Removed stale singleton: {p}")
                except Exception as e:
                    logger.debug(f"Failed to remove stale file/link {p}: {e}")

        chromium_bin = resolve_chromium_bin()
        if not chromium_bin:
            from nova.utils import print_error
            print_error(
                "CRITICAL ERROR: Chromium executable could not be resolved on this system.\n"
                "Nova requires Chromium (searched for 'chromium' in PATH and at /run/current-system/sw/bin/chromium).\n"
                "Please install Chromium or set the CHROMIUM_BIN environment variable to proceed."
            )
            return False

        args = [
            chromium_bin,
            f"--remote-debugging-port={cls.PORT}",
            f"--user-data-dir={cls.AUTOMATED_CHROMIUM_PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-sandbox",
        ]
        if headless:
            args.append("--headless=new")
            args.append("--disable-gpu")

        # Build a clean env with TMPDIR=/tmp to avoid nix-shell private TMPDIR issues
        chromium_env = cls._build_chromium_env()
        logger.debug(f"Launching Chromium with TMPDIR={chromium_env.get('TMPDIR')}")

        try:
            with open(log_file, "a", buffering=1) as log_fp:
                log_fp.write(f"\n--- Launching Chromium at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                log_fp.write(f"Command: {' '.join(args)}\n")
                log_fp.write(f"TMPDIR={chromium_env.get('TMPDIR', '<not set>')}\n")
                proc = subprocess.Popen(
                    args,
                    env=chromium_env,
                    stdout=log_fp,
                    stderr=log_fp,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True
                )
                pid = proc.pid
                pid_file = os.path.join(cls.AUTOMATED_CHROMIUM_PROFILE, "chromium.pid")
                try:
                    with open(pid_file, "w") as f:
                        f.write(str(pid))
                except Exception as e:
                    print_warning(f"Could not save PID file: {e}")

                # 3. Check for immediate process crash
                time.sleep(1.0)
                exit_code = proc.poll()
                if exit_code is not None:
                    diag = cls._collect_failure_diagnostics(
                        chromium_bin, args, exit_code, log_file
                    )
                    print_warning(diag)
                    return False

        except Exception as e:
            print_warning(f"Failed to launch Chromium process: {e}")
            return False

        # 4. Wait for DevTools to become fully available (up to 10 seconds)
        if cls.wait_for_devtools(timeout=10.0):
            if cls.is_process_alive() and cls.get_running_browser_headless_state() == headless:
                print_info("Chromium DevTools is active and listening.")
                return True

        # DevTools failed to respond within timeout — retrieve log output for diagnostics
        diag = cls._collect_failure_diagnostics(
            chromium_bin, args, "(still running but DevTools unresponsive or wrong state)", log_file
        )
        print_warning(f"Failed to start Nova Chromium with remote debugging.\n{diag}")
        return False

    @classmethod
    def restart_browser(cls) -> bool:
        """Kill existing Chromium processes and start a fresh session."""
        print_info("Restarting automated Chromium...")
        cls._terminate_existing_browser()
        from nova.config import CHROMIUM_HEADLESS
        return cls.launch_browser(headless=CHROMIUM_HEADLESS)

    @classmethod
    def get_cdp_url(cls) -> str:
        """Find the responsive CDP URL (preferring localhost, fallback to [::1] or 127.0.0.1)."""
        for host in ["localhost", "127.0.0.1", "[::1]"]:
            url = f"http://{host}:{cls.PORT}"
            try:
                req = urllib.request.Request(f"{url}/json/version")
                with urllib.request.urlopen(req, timeout=0.3) as response:
                    if response.getcode() == 200:
                        return url
            except Exception:
                pass
        return f"http://127.0.0.1:{cls.PORT}"

    @classmethod
    def connect_browser(cls, playwright):
        """Connect to the running Chromium instance over CDP after ensuring DevTools is ready."""
        if not cls.wait_for_devtools(timeout=10.0):
            raise Exception("DevTools verification stage failed: webSocketDebuggerUrl not found.")
        cdp_url = cls.get_cdp_url()
        try:
            conn = playwright.chromium.connect_over_cdp(cdp_url)
            
            # Emit browser_connected to Dashboard
            try:
                from nova.dashboard.event_bus import emit
                emit("browser_connected", module="browser", status="success", metadata={"cdp_url": cdp_url})
            except Exception:
                pass
                
            return conn
        except Exception as e:
            err_msg = str(e)
            if "ECONNRESET" in err_msg or "connection reset" in err_msg.lower():
                print_warning(f"CDP connection stage failed due to connection reset ({err_msg}). Re-launching and retrying...")
                cls.restart_browser()
                if not cls.wait_for_devtools(timeout=10.0):
                    raise Exception("DevTools verification stage failed after browser restart (webSocketDebuggerUrl not found).")
                new_cdp_url = cls.get_cdp_url()
                try:
                    return playwright.chromium.connect_over_cdp(new_cdp_url)
                except Exception as retry_e:
                    raise Exception(f"Failed to connect to Chromium after relaunch. Error: {retry_e}")
            else:
                raise Exception(f"CDP connection stage failed to connect to {cdp_url}. Connection error: {e}") from e

    @classmethod
    def get_persistent_context(cls, browser):
        """
        Safely retrieve the default persistent browser context.
        
        RATIONALE:
        When connecting to Chromium via CDP, the browser instance already has a
        default persistent context created on launch (corresponding to the main user
        profile/data-dir). 
        
        Creating a new context via browser.new_context() creates a new, isolated
        non-persistent (incognito-like) context. This splits the user session,
        causing automation actions to run in a clean sandbox instead of inheriting
        the active user profile, cookies, and state (e.g. login credentials).
        
        Therefore, we must strictly attach to the existing persistent context and
        never create a new one. If no active context is found, we fall back to creating
        a new context to prevent automation failure.
        """
        if not browser.contexts:
            logger.warning("No active browser contexts found. Creating a fallback context.")
            try:
                ctx = browser.new_context()
                cls._attach_context_state_listeners(ctx)
                return ctx
            except Exception as e:
                raise Exception(
                    f"No active browser contexts found, and failed to create a fallback context: {e}"
                )

        # Traverse contexts to find the first active/valid context.
        # The first context in browser.contexts represents the default profile/persistent context.
        for context in browser.contexts:
            try:
                # Accessing .pages validates that the context is active and not closed
                _ = context.pages
                cls._attach_context_state_listeners(context)
                return context
            except Exception:
                continue

        # Fallback: if all existing contexts are invalid/closed, try to create a new one
        logger.warning("All existing browser contexts are inactive or closed. Creating a fallback context.")
        try:
            ctx = browser.new_context()
            cls._attach_context_state_listeners(ctx)
            return ctx
        except Exception as e:
            raise Exception(
                f"No usable browser contexts found, and failed to create a fallback context: {e}"
            )

    @classmethod
    def get_browser(cls, playwright_api=None):
        """
        Retrieve or establish the persistent Playwright CDP connection.
        If the connection is lost or closed, it automatically reconnects.
        """
        # Validate existing browser connection
        if cls._browser is not None and cls._browser.is_connected():
            try:
                # Accessing .contexts checks if the connection is still active/valid
                _ = cls._browser.contexts
                if cls._browser_context is not None:
                    # Access pages to verify context health
                    _ = cls._browser_context.pages
                else:
                    cls._browser_context = cls.get_persistent_context(cls._browser)
                logger.info("Reusing existing browser.")
                return cls._browser
            except Exception:
                # Connection is dead, clean it up
                cls.close_connection()
        else:
            if cls._browser is not None:
                cls.close_connection()

        # Enforce NixOS-safe PLAYWRIGHT_NODEJS_PATH locally to guard against environment corruption
        import shutil
        node_path = "/run/current-system/sw/bin/node"
        if not os.path.exists(node_path):
            node_path = shutil.which("node")
        if node_path:
            os.environ["PLAYWRIGHT_NODEJS_PATH"] = node_path

        # Initialize Playwright if not already done
        if cls._playwright is None:
            if playwright_api is not None:
                cls._playwright = playwright_api
            else:
                try:
                    logger.info("Starting Playwright...")
                    if sync_playwright is None:
                        raise Exception("Playwright sync_api is not installed or available in this environment.")
                    cls._playwright_context_manager = sync_playwright()
                    cls._playwright = cls._playwright_context_manager.start()
                    logger.info("Playwright started.")
                except Exception as e:
                    import traceback
                    err_msg = f"Failed to start Playwright engine: {e}\n{traceback.format_exc()}"
                    logger.error(err_msg)
                    raise Exception(err_msg)

        # Connect to browser over CDP
        try:
            logger.info("Checking CDP endpoint...")
            if not cls.is_cdp_ready():
                logger.error("CDP endpoint not available or not ready.")
                raise Exception("CDP endpoint not ready")
            logger.info("CDP endpoint available.")
            
            logger.info("Connecting to Chromium...")
            cls._browser = cls.connect_browser(cls._playwright)
            cls._browser_context = cls.get_persistent_context(cls._browser)
            logger.info("Connected successfully.")
            return cls._browser
        except Exception as e:
            import traceback
            cls.close_connection()
            err_msg = f"Failed to connect to browser over CDP: {e}\n{traceback.format_exc()}"
            logger.error(err_msg)
            raise Exception(err_msg)

    @classmethod
    def close_connection(cls):
        """Safely close and clean up the persistent browser and Playwright instances."""
        if cls._browser is not None:
            try:
                cls._browser.close()
            except Exception:
                pass
            cls._browser = None
            cls._browser_context = None

        if cls._playwright is not None:
            try:
                cls._playwright.stop()
                logger.info("Playwright stopped.")
            except Exception as e:
                logger.debug(f"Exception during Playwright stop: {e}")
            finally:
                cls._playwright_context_manager = None
                cls._playwright = None

    @classmethod
    def focus_active_window(cls) -> bool:
        """Connect to the running browser and bring the active tab's window to the foreground."""
        try:
            browser = cls.get_browser()
            context = cls.get_persistent_context(browser)
            pages = context.pages
            if pages:
                target_page = None
                for page in pages:
                    try:
                        if page.evaluate("document.visibilityState === 'visible'"):
                            target_page = page
                            break
                    except Exception:
                        pass
                if not target_page:
                    target_page = pages[0]
                cls.focus_browser(target_page)
            else:
                page = context.new_page()
                cls.focus_browser(page)
            return True
        except Exception as e:
            print_warning(f"Failed to focus existing browser window: {e}")
            return False

    @classmethod
    def focus_browser(cls, page) -> None:
        """Bring the specified browser page to the foreground."""
        try:
            page.bring_to_front()
        except Exception:
            pass

    @classmethod
    def _attach_context_state_listeners(cls, context) -> None:
        """Registers automatic event listeners on the BrowserContext."""
        if getattr(context, "_state_listeners_attached", False):
            return
        try:
            context._state_listeners_attached = True
            
            # Listen for new page creation
            def on_page(page):
                cls._attach_page_state_listeners(page)
                cls.trigger_memory_update()
            context.on("page", on_page)

            # Listen for downloads
            def on_download(download):
                cls._handle_download(download)
            context.on("download", on_download)

            # Attach to existing pages
            for page in context.pages:
                cls._attach_page_state_listeners(page)
                
            logger.debug("Attached state listeners to Playwright BrowserContext.")
        except Exception as e:
            logger.debug(f"Failed to attach context state listeners: {e}")

    @classmethod
    def _attach_page_state_listeners(cls, page) -> None:
        """Registers event-driven triggers on a Playwright Page."""
        if getattr(page, "_state_listeners_attached", False):
            return
        try:
            page._state_listeners_attached = True
            
            # Hook navigation and lifecycle events
            page.on("framenavigated", lambda frame: cls.trigger_memory_update())
            page.on("load", lambda p: cls.trigger_memory_update())
            page.on("close", lambda p: cls.trigger_memory_update())
        except Exception as e:
            logger.debug(f"Failed to attach page state listeners: {e}")

    @classmethod
    def _handle_download(cls, download) -> None:
        """Safely records download events in working memory."""
        logger.info(f"Detected browser download event: {download.suggested_filename}")
        if cls._working_memory is None:
            return
        try:
            downloads = list(cls._working_memory.get("download_activity") or [])
            # Avoid duplicate writes
            url = download.url
            filename = download.suggested_filename
            dup = any(d.get("url") == url and d.get("filename") == filename for d in downloads)
            if not dup:
                downloads.append({
                    "filename": filename,
                    "url": url,
                    "timestamp": time.time()
                })
                cls._working_memory.set("download_activity", downloads)
                logger.info(f"Recorded download in Working Memory: {filename}")
                try:
                    cls._working_memory.history_manager.add_entry(
                        "browser_event",
                        f"Browser download initiated: {filename}",
                        {"filename": filename, "url": url}
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Failed to record download activity in Working Memory: {e}")

    @classmethod
    def trigger_memory_update(cls) -> None:
        """Callbacks to update Working Memory dynamically when browser state shifts."""
        if cls._working_memory is None:
            return
        try:
            cls.update_browser_memory_state(cls._working_memory)
        except Exception as e:
            logger.debug(f"Failed to trigger browser memory update: {e}")

    @classmethod
    def update_browser_memory_state(cls, working_memory) -> None:
        """
        Queries Playwright context, extracts pages, title, URL, tabs count, domain,
        search engine query details, and updates working memory attributes.
        """
        from urllib.parse import urlparse, parse_qs
        
        if not cls.is_browser_running():
            # Reset values if browser is closed
            working_memory.set("current_browser", None)
            working_memory.set("current_tab", None)
            working_memory.set("tab_title", None)
            working_memory.set("current_url", None)
            working_memory.set("domain", None)
            working_memory.set("search_engine", None)
            working_memory.set("current_search_query", None)
            working_memory.set("open_tabs_count", 0)
            return

        try:
            browser = cls.get_browser()
            if browser is None or not browser.is_connected():
                return
            context = cls.get_persistent_context(browser)
            pages = context.pages
        except Exception:
            return
        
        # Determine open tabs count
        open_tabs_count = len(pages)
        working_memory.set("open_tabs_count", open_tabs_count)

        # Get active page
        try:
            from nova.browser_helper import find_active_page
            active_page = find_active_page(context)
        except Exception:
            active_page = pages[0] if pages else None
        
        if active_page:
            # Active browser
            working_memory.set("current_browser", "Chromium")
            
            # Tab title and URL
            try:
                title = active_page.title()
                url = active_page.url
            except Exception:
                return
            
            working_memory.set("tab_title", title)
            working_memory.set("current_url", url)
            
            # Parse domain and query
            domain = None
            search_engine = None
            search_query = None
            
            if url and url != "about:blank":
                parsed = urlparse(url)
                domain = parsed.netloc
                working_memory.set("domain", domain)
                
                # Set active tab identifier (using url hash)
                working_memory.set("current_tab", f"tab_{hash(url) & 0xffff}")
                
                # Check search engines
                domain_lower = domain.lower()
                if "google." in domain_lower:
                    search_engine = "Google"
                    queries = parse_qs(parsed.query)
                    if "q" in queries:
                        search_query = queries["q"][0]
                elif "bing." in domain_lower:
                    search_engine = "Bing"
                    queries = parse_qs(parsed.query)
                    if "q" in queries:
                        search_query = queries["q"][0]
                elif "duckduckgo." in domain_lower:
                    search_engine = "DuckDuckGo"
                    queries = parse_qs(parsed.query)
                    if "q" in queries:
                        search_query = queries["q"][0]
                elif "yahoo." in domain_lower:
                    search_engine = "Yahoo"
                    queries = parse_qs(parsed.query)
                    if "p" in queries:
                        search_query = queries["p"][0]
                        
                working_memory.set("search_engine", search_engine)
                working_memory.set("current_search_query", search_query)
                
                # History Context
                try:
                    history = list(working_memory.get("navigation_history") or [])
                    # Avoid duplicate history entries
                    if not history or history[-1] != url:
                        history.append(url)
                        working_memory.set("navigation_history", history)
                        try:
                            working_memory.history_manager.add_entry(
                                "browser_event",
                                f"Browser navigated to: {url}",
                                {"url": url, "title": title}
                            )
                        except Exception:
                            pass
                except Exception as hist_err:
                    logger.debug(f"History logging failed: {hist_err}")
            else:
                working_memory.set("domain", None)
                working_memory.set("current_tab", "about:blank")
                working_memory.set("search_engine", None)
                working_memory.set("current_search_query", None)
        else:
            working_memory.set("current_browser", None)
            working_memory.set("current_tab", None)
            working_memory.set("tab_title", None)
            working_memory.set("current_url", None)
            working_memory.set("domain", None)
            working_memory.set("search_engine", None)
            working_memory.set("current_search_query", None)

# Register the atexit hook to cleanly close the persistent Playwright CDP connection on exit
atexit.register(BrowserManager.close_connection)
