import sys
import os
import glob
import json
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
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

import json
import socket
from nova.ai import OllamaClient
from nova.parser import parse_and_validate_action
from nova.actions import get_action_dispatcher
from nova.executor import CommandExecutor
from nova.history import HistoryManager
from nova.utils import (
    print_banner,
    print_success,
    print_info,
    print_error,
    print_warning,
    COLOR_BOLD,
    COLOR_CYAN,
    COLOR_RED,
    COLOR_RESET,
    set_socket_conn
)

def run_daemon() -> None:
    print_info("Starting Nova daemon...")
    
    # Start Dashboard Server
    try:
        from nova.dashboard import start_dashboard
        start_dashboard()
    except Exception as e:
        print_error(f"Failed to start dashboard: {e}")
        
    ai_client = OllamaClient()
    dispatcher = get_action_dispatcher()
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", 11435))
    except Exception as e:
        print_error(f"Failed to bind socket on port 11435. Is another instance running? {e}")
        sys.exit(1)
        
    server.listen(5)
    print_info("Nova daemon listening on 127.0.0.1:11435")
    
    # Initialize and start voice loop in background thread
    from nova.voice.conversation import run_voice_loop, shutdown_event
    import threading
    import time
    from nova.browser_manager import BrowserManager
    
    shutdown_event.clear()
    
    def voice_thread_target():
        while not shutdown_event.is_set():
            try:
                run_voice_loop(ai_client, dispatcher)
            except Exception as e:
                import logging
                logging.getLogger("nova").error(f"Daemon voice loop error: {e}")
                import traceback
                traceback.print_exc()
            if shutdown_event.is_set():
                break
            time.sleep(1)
            
    t = threading.Thread(target=voice_thread_target, daemon=True)
    t.start()
    print_info("Nova voice loop initialized in background.")
    
    # Start Telegram Bot remote command listener polling loop
    try:
        from nova.services.telegram import TelegramService
        tg_service = TelegramService()
        tg_service.start_polling(ai_client, dispatcher)
    except Exception as e:
        print_error(f"Failed to start Telegram listener: {e}")
    
    while True:
        original_env = None
        try:
            conn, addr = server.accept()
            # Receive query command (up to 64KB to cover large environments)
            data = conn.recv(65536).decode("utf-8").strip()
            if not data:
                conn.close()
                continue
            
            # Route printing and console input prompts to the socket
            set_socket_conn(conn)
            CommandExecutor.clear_last_commands()
            
            original_env = dict(os.environ)
            query = data
            if data.startswith("NOVA_JSON:"):
                try:
                    payload = json.loads(data[10:])
                    if isinstance(payload, dict) and "query" in payload:
                        query = payload["query"]
                        client_env = payload.get("env", {})
                        if isinstance(client_env, dict):
                            # Allow only specific GUI and standard Nix variables (Security check)
                            SAFE_ENV_ALLOWLIST = {
                                "DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS", 
                                "PATH", "LANG", "LC_ALL", "XDG_RUNTIME_DIR",
                                "CHROMIUM_BIN", "CHROME_BIN"
                            }
                            filtered_env = {k: v for k, v in client_env.items() if k in SAFE_ENV_ALLOWLIST}
                            os.environ.update(filtered_env)
                        client_chromium_bin = payload.get("chromium_bin") or payload.get("chrome_bin")
                        if client_chromium_bin:
                            os.environ["CHROMIUM_BIN"] = client_chromium_bin
                            os.environ["CHROME_BIN"] = client_chromium_bin
                except (json.JSONDecodeError, TypeError):
                    pass

            if query == "ACTIVATE_VOICE":
                from nova.voice.conversation import get_current_state, VoiceState, voice_active_event
                state = get_current_state()
                if state in (VoiceState.VOICE_IDLE, VoiceState.TEXT_MODE, VoiceState.INACTIVE):
                    from nova.voice.conversation import transition_state
                    transition_state(VoiceState.VOICE_IDLE)
                    voice_active_event.set()
                    conn.sendall(b"Nova voice activation triggered.\n")
                else:
                    conn.sendall(f"Nova is already active (State: {state.name}).\n".encode("utf-8"))
                conn.close()
                set_socket_conn(None)
                continue

            if query == "TOGGLE_VOICE":
                from nova.voice.conversation import get_current_state, VoiceState, voice_active_event, transition_state, set_deferred_deactivate
                state = get_current_state()
                if state in (VoiceState.INACTIVE, VoiceState.TEXT_MODE):
                    # Activate!
                    transition_state(VoiceState.VOICE_IDLE)
                    voice_active_event.set()
                    conn.sendall(b"Nova is now listening.\n")
                else:
                    # Deactivate immediately — covers VOICE_IDLE, PUSH_TO_TALK,
                    # LISTENING, TRANSCRIBING, EXECUTING, SPEAKING, WAKE_DETECTED.
                    # The recorder and voice loop both check _current_state and will
                    # exit their inner loops as soon as they see INACTIVE.
                    transition_state(VoiceState.INACTIVE)
                    conn.sendall(b"Nova has stopped listening.\n")
                conn.close()
                set_socket_conn(None)
                continue

            if query == "STATUS":
                from nova.voice.conversation import get_voice_status_report
                try:
                    report = get_voice_status_report()
                    conn.sendall(json.dumps(report).encode("utf-8"))
                except Exception as e:
                    conn.sendall(f"Error generating status: {e}".encode("utf-8"))
                continue

            try:
                from nova.spelling import correct_query_spelling, correct_action_data
                query = correct_query_spelling(query)
                
                # Check for autonomous mode toggle commands
                from nova.state import StateManager
                handled = False
                query_lower = query.lower().strip()
                if any(cmd in query_lower for cmd in ("enable autonomous", "turn on autonomous", "make your own decision", "go autonomous", "enable auto mode")):
                    StateManager.set_autonomous_mode(True)
                    conn.sendall(b"Nova Autonomous Mode is now ENABLED.\n")
                    handled = True
                elif any(cmd in query_lower for cmd in ("disable autonomous", "turn off autonomous", "ask for confirmation", "stop making decision", "disable auto mode")):
                    StateManager.set_autonomous_mode(False)
                    conn.sendall(b"Nova Autonomous Mode is now DISABLED.\n")
                    handled = True
                elif any(cmd in query_lower for cmd in ("check autonomous", "status of autonomous", "is autonomous mode")):
                    status = "ENABLED" if StateManager.is_autonomous() else "DISABLED"
                    conn.sendall(f"Nova Autonomous Mode is currently {status}.\n".encode("utf-8"))
                    handled = True
                elif query_lower in ("history", "show history", "view history", "list history"):
                    HistoryManager.print_history()
                    handled = True
                
                if handled:
                    conn.close()
                    continue

                raw_response = ai_client.parse_intent(query)
                if not raw_response:
                    print_error("Failed to connect to Ollama or parse the request. Please check if Ollama is running.")
                    HistoryManager.add_entry(query, {}, CommandExecutor.get_last_commands(), "ollama_failed")
                    conn.close()
                    continue
                    
                actions_list = parse_and_validate_action(raw_response)
                if not actions_list:
                    print_error("Could not determine or parse action intent from AI response.")
                    print_warning(f"Raw Response: {raw_response.strip()}")
                    HistoryManager.add_entry(query, {}, CommandExecutor.get_last_commands(), "parse_failed")
                    conn.close()
                    continue
                    
                for action_data in actions_list:
                    action_data = correct_action_data(action_data, query)
                    action_name = action_data.get("action")
                    action_handler = dispatcher.get(action_name)
                    
                    if not action_handler:
                        print_error(f"Intent recognized as '{action_name}', but no action handler is registered.")
                        HistoryManager.add_entry(query, action_data, CommandExecutor.get_last_commands(), "no_handler")
                        continue
                        
                    print_info(f"Action parsed: {action_name}")
                    
                    # Publish to Dashboard
                    try:
                        from nova.dashboard.event_bus import emit
                        emit("action_parsed", module="core", status="running", metadata={"action": action_name, "parameters": action_data})
                        emit("plugin_triggered", module="plugins", status="running", metadata={"plugin": action_name, "parameters": action_data})
                    except Exception:
                        pass
                        
                    result_message = action_handler.execute(action_data)
                    
                    if "error" in result_message.lower() or "failed" in result_message.lower():
                        print_error(result_message)
                        status = "execution_failed"
                    elif "aborted" in result_message.lower() or "cancelled" in result_message.lower():
                        print_warning(result_message)
                        status = "aborted"
                    else:
                        print_success(result_message)
                        status = "success"
                        
                    # Publish to Dashboard
                    try:
                        from nova.dashboard.event_bus import emit
                        emit("task_completed", module="core", status="success" if status == "success" else "failed", metadata={"action": action_name, "message": result_message, "status_code": status})
                    except Exception:
                        pass
                        
                    HistoryManager.add_entry(query, action_data, CommandExecutor.get_last_commands(), status, result_message=result_message)
            except Exception as e:
                try:
                    conn.sendall(f"{COLOR_RED}Exception occurred: {e}{COLOR_RESET}\n".encode("utf-8"))
                except Exception:
                    pass
                HistoryManager.add_entry(query, {}, CommandExecutor.get_last_commands(), "exception_raised")
            finally:
                # Restore original environment
                if original_env is not None:
                    os.environ.clear()
                    os.environ.update(original_env)
                set_socket_conn(None)
                try:
                    conn.close()
                except Exception:
                    pass
        except KeyboardInterrupt:
            print_info("Daemon shutting down.")
            break
        except Exception as e:
            print_error(f"Daemon socket error: {e}")

    print_info("Initiating graceful shutdown...")
    shutdown_event.set()
    try:
        t.join(timeout=2.0)
    except Exception:
        pass
    
    # Stop Dashboard Server
    try:
        from nova.dashboard import stop_dashboard
        stop_dashboard()
    except Exception as e:
        print_error(f"Failed to stop dashboard: {e}")
        
    print_info("Closing browser connection...")
    BrowserManager.close_connection()
    print_info("Closing daemon socket...")
    try:
        server.close()
    except Exception:
        pass
    print_info("Graceful shutdown complete.")

def run_client(query: str) -> None:
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect(("127.0.0.1", 11435))
    except Exception:
        print_error("Failed to connect to Nova daemon. Is it running? Start it with: nova start")
        sys.exit(1)
        
    from nova.utils import resolve_chromium_bin
    resolved_chromium = resolve_chromium_bin()

    payload = {
        "query": query,
        "env": dict(os.environ),
        "chromium_bin": resolved_chromium,
        "chrome_bin": resolved_chromium
    }
    message = f"NOVA_JSON:{json.dumps(payload)}"
    client.sendall(message.encode("utf-8"))
    
    while True:
        try:
            data = client.recv(4096)
            if not data:
                break
            text = data.decode("utf-8")
            
            # Format status response if received
            if text.startswith('{"running":'):
                try:
                    status = json.loads(text)
                    print(f"● Nova Assistant Service")
                    print(f"   Background Service Health: {status['health']}")
                    print(f"   Current State:             {status['state']}")
                    print(f"   Microphone:                {status['microphone']}")
                    print(f"   Wake-Word Engine:          {status['wake_word']}")
                    print(f"   Whisper (STT):             {status['whisper']}")
                    print(f"   ElevenLabs (TTS):          {status['elevenlabs']}")
                    print(f"   Browser Automation:        {status['browser']}")
                except Exception:
                    pass
                break
            
            # Check if prompt requires a y/n confirmation
            if "(y/n):" in text:
                choice = input(text)
                client.sendall(choice.encode("utf-8"))
            else:
                sys.stdout.write(text)
                sys.stdout.flush()
        except KeyboardInterrupt:
            print()
            break
    client.close()

def get_greeting() -> str:
    from nova.state import StateManager
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
            from nova.voice.voice_setup import main as voice_setup_main
            voice_setup_main()
            return
        elif cmd == "voice-reset":
            from nova.voice.voice_reset import main as voice_reset_main
            voice_reset_main()
            return
        elif cmd == "voice-test":
            from nova.voice.voice_test import main as voice_test_main
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
    print_banner()
    from nova.voice.config import enable_debug
    if enable_debug:
        print_info("Initializing Nova intent parser...")
    
    # Initialize components
    ai_client = OllamaClient()
    dispatcher = get_action_dispatcher()
    
    if enable_debug:
        print_info(f"Loaded {len(dispatcher)} action handlers dynamically.")
    
    # Startup voice dependency check
    try:
        from nova.voice import check_voice_dependencies
        missing_voice_deps = check_voice_dependencies()
        if missing_voice_deps:
            print_warning("\n[Startup Warning] Some optional voice dependencies are missing:")
            for dep, reason in missing_voice_deps:
                print(f"  - {dep} (Reason: {reason})")
            print_info("To install them, activate your virtual environment and run:")
            print_info("  source .venv/bin/activate && pip install -r requirements-voice.txt\n")
    except Exception as e:
        pass
    
    first_run = True
    while True:
        if first_run:
            first_run = False
            if "--text" in args:
                mode = "1"
            else:
                mode = "2"
        else:
            print("================================")
            print("1. Text Mode")
            print("2. Voice Mode")
            print("================================")
            
            mode = ""
            while mode not in ("1", "2"):
                try:
                    mode = input("Select mode (1/2): ").strip()
                except (KeyboardInterrupt, EOFError):
                    print()
                    print_info("Goodbye!")
                    return

        if mode == "2":
            try:
                from nova.voice import check_voice_dependencies
                from nova.voice.conversation import run_voice_loop
                voice_issues = check_voice_dependencies()
                if voice_issues:
                    print_error("Voice mode is unavailable.\n")
                    for dep, reason in voice_issues:
                        print(f"Missing dependency:\n{dep}\n")
                        print(f"Reason:\n{reason}\n")
                    continue
                result = run_voice_loop(ai_client, dispatcher, interactive=True)
            except ModuleNotFoundError as e:
                missing_pkg = e.name if hasattr(e, 'name') and e.name else str(e)
                print_error("Voice mode is unavailable.\n")
                print(f"Missing dependency:\n{missing_pkg}\n")
                print(f"Reason:\nNo module named '{missing_pkg}'\n")
                continue

            if result == "text":
                mode = "1"
            elif result == "menu":
                continue
            else:
                return

        if mode == "1":
            break

    greeting = get_greeting()
    print_success(f"{greeting} How can I help you today?")
    print_info("Ask Nova to do something (e.g., 'Open Chrome', 'Install vlc')")
    print_info("Type 'exit' or 'quit' to close the assistant.\n")
    
    while True:
        try:
            # Styled prompt
            prompt_str = f"{COLOR_CYAN}{COLOR_BOLD}nova ❯ {COLOR_RESET}"
            user_input = input(prompt_str).strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ("exit", "quit"):
                print_info("Goodbye!")
                break
                
            # Check for direct voice subsystem commands in REPL
            cmd_lower = user_input.lower().strip()
            if cmd_lower == "voice-setup":
                from nova.voice.voice_setup import main as voice_setup_main
                try:
                    voice_setup_main()
                except Exception as e:
                    print_error(f"Voice setup failed: {e}")
                continue
            elif cmd_lower == "voice-reset":
                from nova.voice.voice_reset import main as voice_reset_main
                try:
                    voice_reset_main()
                except Exception as e:
                    print_error(f"Voice reset failed: {e}")
                continue
            elif cmd_lower == "voice-test":
                from nova.voice.voice_test import main as voice_test_main
                try:
                    voice_test_main()
                except Exception as e:
                    print_error(f"Voice test failed: {e}")
                continue

            # Clear command buffer for new turn
            CommandExecutor.clear_last_commands()
            
            from nova.spelling import correct_query_spelling, correct_action_data
            user_input = correct_query_spelling(user_input)
            
            # Check for autonomous mode toggle commands
            from nova.state import StateManager
            handled = False
            ui_lower = user_input.lower().strip()
            if any(cmd in ui_lower for cmd in ("enable autonomous", "turn on autonomous", "make your own decision", "go autonomous", "enable auto mode")):
                StateManager.set_autonomous_mode(True)
                handled = True
            elif any(cmd in ui_lower for cmd in ("disable autonomous", "turn off autonomous", "ask for confirmation", "stop making decision", "disable auto mode")):
                StateManager.set_autonomous_mode(False)
                handled = True
            elif any(cmd in ui_lower for cmd in ("check autonomous", "status of autonomous", "is autonomous mode")):
                status = "ENABLED" if StateManager.is_autonomous() else "DISABLED"
                print(f"Nova Autonomous Mode is currently {status}.")
                handled = True
            elif ui_lower in ("history", "show history", "view history", "list history"):
                HistoryManager.print_history()
                handled = True
                
            if handled:
                continue

            print(f"{COLOR_BOLD}Thinking...{COLOR_RESET}", end="\r")
            raw_response = ai_client.parse_intent(user_input)
            
            # Clear the "Thinking..." line
            print(" " * 20, end="\r")
            
            if not raw_response:
                print_error("Failed to connect to Ollama or parse the request. Please check if Ollama is running.")
                HistoryManager.add_entry(
                    user_input=user_input,
                    parsed_action={},
                    executed_commands=CommandExecutor.get_last_commands(),
                    status="ollama_failed"
                )
                continue
                
            actions_list = parse_and_validate_action(raw_response)
            if not actions_list:
                print_error("Could not determine or parse action intent from AI response.")
                print_warning(f"Raw Response: {raw_response.strip()}")
                HistoryManager.add_entry(
                    user_input=user_input,
                    parsed_action={},
                    executed_commands=CommandExecutor.get_last_commands(),
                    status="parse_failed"
                )
                continue
            for action_data in actions_list:
                action_data = correct_action_data(action_data, user_input)
                action_name = action_data.get("action")
                action_handler = dispatcher.get(action_name)
                
                if not action_handler:
                    print_error(f"Intent recognized as '{action_name}', but no action handler is registered.")
                    HistoryManager.add_entry(
                        user_input=user_input,
                        parsed_action=action_data,
                        executed_commands=CommandExecutor.get_last_commands(),
                        status="no_handler"
                    )
                    continue
                    
                # Execute parsed action
                try:
                    # Log execution info
                    print_info(f"Action parsed: {action_name}")
                    
                    # Publish to Dashboard
                    try:
                        from nova.dashboard.event_bus import emit
                        emit("action_parsed", module="core", status="running", metadata={"action": action_name, "parameters": action_data})
                        emit("plugin_triggered", module="plugins", status="running", metadata={"plugin": action_name, "parameters": action_data})
                    except Exception:
                        pass
                        
                    result_message = action_handler.execute(action_data)
                    
                    if "error" in result_message.lower() or "failed" in result_message.lower():
                        print_error(result_message)
                        status = "execution_failed"
                    elif "aborted" in result_message.lower() or "cancelled" in result_message.lower():
                        print_warning(result_message)
                        status = "aborted"
                    else:
                        print_success(result_message)
                        status = "success"
                        
                    # Publish to Dashboard
                    try:
                        from nova.dashboard.event_bus import emit
                        emit("task_completed", module="core", status="success" if status == "success" else "failed", metadata={"action": action_name, "message": result_message, "status_code": status})
                    except Exception:
                        pass
                        
                    # Save to history
                    HistoryManager.add_entry(
                        user_input=user_input,
                        parsed_action=action_data,
                        executed_commands=CommandExecutor.get_last_commands(),
                        status=status,
                        result_message=result_message
                    )
                except Exception as e:
                    print_error(f"An exception occurred while executing action: {e}")
                    HistoryManager.add_entry(
                        user_input=user_input,
                        parsed_action=action_data,
                        executed_commands=CommandExecutor.get_last_commands(),
                        status="exception_raised"
                    )
                
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            print() # Print newline
            print_info("Interrupt received. Type 'exit' to quit or continue.")
        except EOFError:
            # Handle Ctrl+D gracefully
            print()
            print_info("Goodbye!")
            break
        except Exception as e:
            print_error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
