import sys
import os
import json
import socket
import signal
from nova.ai.ollama import OllamaClient
from nova.parser import parse_and_validate_action
from nova.actions import get_action_dispatcher
from nova.core.executor import CommandExecutor
from nova.core.memory import HistoryManager, WorkingMemory
from nova.core.state import StateManager
from nova.utils import (
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
    wm = WorkingMemory()

    # Restore persistent battery charging limit if configured
    try:
        limit = StateManager.get_charge_limit()
        if limit is not None:
            print_info(f"Restoring persistent battery charging limit: {limit}%")
            from nova.actions.charge_control import ChargeControlAction
            action = ChargeControlAction()
            action.execute({"operation": "set", "level": limit})
    except Exception as e:
        print_warning(f"Failed to restore persistent battery charging limit: {e}")
    
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
    from nova.voice.pipeline import run_voice_loop, shutdown_event
    import threading
    import time
    from nova.browser.manager import BrowserManager
    
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
                from nova.voice.pipeline import get_current_state, VoiceState, voice_active_event
                state = get_current_state()
                if state in (VoiceState.VOICE_IDLE, VoiceState.TEXT_MODE, VoiceState.INACTIVE):
                    from nova.voice.pipeline import transition_state
                    transition_state(VoiceState.VOICE_IDLE)
                    voice_active_event.set()
                    conn.sendall(b"Nova voice activation triggered.\n")
                else:
                    conn.sendall(f"Nova is already active (State: {state.name}).\n".encode("utf-8"))
                conn.close()
                set_socket_conn(None)
                continue

            if query == "TOGGLE_VOICE":
                from nova.voice.pipeline import get_current_state, VoiceState, voice_active_event, transition_state
                state = get_current_state()
                if state in (VoiceState.INACTIVE, VoiceState.TEXT_MODE):
                    # Activate!
                    transition_state(VoiceState.VOICE_IDLE)
                    voice_active_event.set()
                    conn.sendall(b"Nova is now listening.\n")
                else:
                    transition_state(VoiceState.INACTIVE)
                    conn.sendall(b"Nova has stopped listening.\n")
                conn.close()
                set_socket_conn(None)
                continue

            if query == "STATUS":
                from nova.voice.pipeline import get_voice_status_report
                try:
                    report = get_voice_status_report()
                    conn.sendall(json.dumps(report).encode("utf-8"))
                except Exception as e:
                    conn.sendall(f"Error generating status: {e}".encode("utf-8"))
                continue

            try:
                from nova.spelling import correct_query_spelling
                query = correct_query_spelling(query)
                
                # Check for autonomous mode toggle commands
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

                from nova.ai.planner import Goal
                from nova.ai.reasoning import route_query_to_planner_pipeline
                
                # Check autonomous state to determine if approval is required
                approval_required = not StateManager.is_autonomous()
                
                # Set up goal carrying NLP actions list as metadata for dynamic planners
                goal = Goal(description=query)
                goal.metadata = {"actions": actions_list}
                
                result_message = route_query_to_planner_pipeline(
                    query=query,
                    working_memory=wm,
                    dispatcher=dispatcher,
                    approval_required=approval_required,
                    actions=actions_list
                )
                
                if "error" in result_message.lower() or "failed" in result_message.lower():
                    status = "execution_failed"
                elif "aborted" in result_message.lower() or "cancelled" in result_message.lower():
                    status = "aborted"
                else:
                    status = "success"
                    
                # Publish to Dashboard
                try:
                    from nova.dashboard.event_bus import emit
                    emit("task_completed", module="core", status="success" if status == "success" else "failed", metadata={"goal": query, "message": result_message, "status_code": status})
                except Exception:
                    pass
                    
                HistoryManager.add_entry(query, {}, CommandExecutor.get_last_commands(), status, result_message=result_message)
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
