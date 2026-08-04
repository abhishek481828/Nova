import sys
import os
from nova.ai.ollama import OllamaClient
from nova.parser import parse_and_validate_action
from nova.actions import get_action_dispatcher
from nova.core.executor import CommandExecutor
from nova.core.memory import HistoryManager, get_working_memory
from nova.core.state import StateManager
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
)
from nova.core.orchestrator import get_greeting

def run_cli_repl(args=None) -> None:
    if args is None:
        args = []
        
    print_banner()
    from nova.voice.config import enable_debug
    if enable_debug:
        print_info("Initializing Nova intent parser...")
    
    # Initialize components
    wm = get_working_memory()
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
    except Exception:
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
                from nova.voice.pipeline import run_voice_loop
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

            # Phone Control Natural Language Shortcuts
            if any(phrase in cmd_lower for phrase in ("connect phone", "connect to phone", "phone connect", "nova connect phone")):
                action_res = dispatcher["phone_connect"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("turn on phone flash", "turn on flashlight", "flash on", "flashlight on", "turn on flash", "enable flashlight", "on phone flash")):
                action_res = dispatcher["phone_flashlight"].execute({"state": "on"})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("turn off phone flash", "turn off flashlight", "flash off", "flashlight off", "turn off flash", "disable flashlight", "off phone flash")):
                action_res = dispatcher["phone_flashlight"].execute({"state": "off"})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("vibrate phone", "phone vibrate")):
                action_res = dispatcher["phone_vibrate"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("decrease phone volume", "lower phone volume", "reduce phone volume", "phone volume down")):
                import re as _re
                nums = _re.findall(r'\d+', user_input)
                level = int(nums[0]) if nums else 10
                action_res = dispatcher["phone_volume"].execute({"operation": "decrease", "level": level})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("increase phone volume", "raise phone volume", "phone volume up")):
                import re as _re
                nums = _re.findall(r'\d+', user_input)
                level = int(nums[0]) if nums else 10
                action_res = dispatcher["phone_volume"].execute({"operation": "increase", "level": level})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("mute my phone", "mute phone", "phone mute")):
                action_res = dispatcher["phone_volume"].execute({"operation": "mute"})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("set phone volume", "phone volume set", "phone volume to")):
                import re as _re
                nums = _re.findall(r'\d+', user_input)
                level = int(nums[0]) if nums else 50
                action_res = dispatcher["phone_volume"].execute({"operation": "set", "level": level})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("take photo", "capture photo", "snap photo", "take a photo")):
                facing = "front" if "front" in cmd_lower else "back"
                action_res = dispatcher["phone_camera"].execute({"operation": "capture_photo", "camera_selector": facing})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("record video", "record phone video", "take video")):
                import re as _re
                nums = _re.findall(r'\d+', user_input)
                dur = int(nums[0]) if nums else 5
                facing = "front" if "front" in cmd_lower else "back"
                action_res = dispatcher["phone_camera"].execute({"operation": "record_video", "camera_selector": facing, "duration_seconds": dur})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("scan qr", "scan qr code", "qr scanner")):
                action_res = dispatcher["phone_camera"].execute({"operation": "scan_qr"})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("ocr scan", "extract text from camera", "phone ocr")):
                action_res = dispatcher["phone_camera"].execute({"operation": "ocr_scan"})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("phone gallery", "show gallery", "list gallery", "gallery items")):
                import re as _re
                nums = _re.findall(r'\d+', user_input)
                limit = int(nums[0]) if nums else 5
                action_res = dispatcher["phone_gallery"].execute({"operation": "get_recent", "limit": limit})
                print_success(action_res)
                continue
            elif "on phone" not in cmd_lower and any(phrase in cmd_lower for phrase in ("view photo", "open photo", "see photo", "show photo", "view image", "open image")):
                import re as _re
                nums = _re.findall(r'\d+', user_input)
                idx = int(nums[0]) if nums else 1
                action_res = dispatcher["phone_gallery"].execute({"operation": "view", "index": idx})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("upload photo", "upload media", "upload to server")):
                action_res = dispatcher["phone_media_upload"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("list phone apps", "show phone apps", "list apps on phone", "installed phone apps")):
                inc_sys = True if "system" in cmd_lower else False
                action_res = dispatcher["app_list"].execute({"include_system": inc_sys})
                print_success(action_res)
                continue
            elif "youtube" in cmd_lower and any(kw in cmd_lower for kw in ("search", "play", "find")):
                import re as _re
                m = _re.search(r"^(?:search|play|find)\s+(.+?)\s+on\s+youtube(?:\s+(?:in|on)\s+phone)?$", cmd_lower)
                if not m:
                    m = _re.search(r"^(?:search|find)\s+youtube\s+for\s+(.+?)(?:\s+(?:in|on)\s+phone)?$", cmd_lower)
                if m:
                    yt_query = m.group(1).strip()
                    action_res = dispatcher["app_launch"].execute({"app_name": "youtube", "search_query": yt_query})
                    print_success(action_res)
                    continue
            elif "whatsapp" in cmd_lower and any(kw in cmd_lower for kw in ("call", "voice call", "message", "msg")):
                import re as _re
                m = _re.search(r"^(?:call|voice call)\s+(.+?)\s+on\s+whatsapp(?:\s+(?:in|on)\s+phone)?$", cmd_lower)
                if m:
                    contact = m.group(1).strip()
                    action_res = dispatcher["app_launch"].execute({"app_name": "whatsapp", "contact_name": contact, "operation": "call"})
                    print_success(action_res)
                    continue
            elif "on phone" in cmd_lower and any(cmd_lower.startswith(p) for p in ("open ", "launch ")):
                import re as _re
                match = _re.search(r"^(?:open|launch)\s+(.+?)\s+on\s+phone$", cmd_lower)
                if match:
                    app_target = match.group(1).strip()
                    action_res = dispatcher["app_launch"].execute({"app_name": app_target})
                    print_success(action_res)
                    continue
            elif any(phrase in cmd_lower for phrase in ("take screenshot", "take screenshot on phone", "screen capture", "screenshot phone", "take a screenshot")):
                action_res = dispatcher["screen_capture"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("start screen recording", "record phone screen", "start recording phone screen", "start recording")):
                action_res = dispatcher["screen_record_start"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("stop screen recording", "stop recording phone screen", "stop recording")):
                action_res = dispatcher["screen_record_stop"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("start screen stream", "start screen streaming", "start screen sharing")):
                action_res = dispatcher["screen_stream_start"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("stop screen stream", "stop screen streaming", "stop screen sharing")):
                action_res = dispatcher["screen_stream_stop"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("get screen state", "screen state", "check screen state", "screen status")):
                action_res = dispatcher["screen_state_get"].execute({})
                print_success(action_res)
                continue
            elif any(cmd_lower.startswith(p) for p in ("tap ", "click ")) and any(char.isdigit() for char in cmd_lower):
                import re as _re
                match = _re.search(r"^(?:tap|click)\s+(?:at\s+)?(\d+)\s+(\d+)(?:\s+on\s+phone)?$", cmd_lower)
                if match:
                    x, y = float(match.group(1)), float(match.group(2))
                    action_res = dispatcher["screen_tap"].execute({"x": x, "y": y})
                    print_success(action_res)
                    continue
            elif any(phrase in cmd_lower for phrase in ("start voice session", "start voice session on phone", "start voice mode")):
                action_res = dispatcher["voice_session_start"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("stop voice session", "stop voice session on phone", "stop voice mode")):
                action_res = dispatcher["voice_session_stop"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("mic on", "open mic", "start mic", "listen", "start audio capture", "start mic capture")):
                action_res = dispatcher["audio_capture_start"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("mic off", "close mic", "stop mic", "stop audio capture", "stop mic capture")):
                action_res = dispatcher["audio_capture_stop"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("mute mic", "mute microphone", "mute phone mic")):
                action_res = dispatcher["microphone_mute"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("unmute mic", "unmute microphone", "unmute phone mic")):
                action_res = dispatcher["microphone_unmute"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("go home on phone", "press home on phone")):
                action_res = dispatcher["global_gesture"].execute({"gesture": "home"})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("go back on phone", "press back on phone")):
                action_res = dispatcher["global_gesture"].execute({"gesture": "back"})
                print_success(action_res)
                continue
            elif "scroll down" in cmd_lower and "phone" in cmd_lower:
                action_res = dispatcher["accessibility_scroll"].execute({"direction": "down"})
                print_success(action_res)
                continue
            elif "scroll up" in cmd_lower and "phone" in cmd_lower:
                action_res = dispatcher["accessibility_scroll"].execute({"direction": "up"})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("device info", "phone info", "check device info")):
                action_res = dispatcher["device_info"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("device health", "phone health", "check device health")):
                action_res = dispatcher["device_health"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("device storage", "phone storage", "check storage")):
                action_res = dispatcher["device_storage"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("device memory", "phone memory", "phone ram", "check ram")):
                action_res = dispatcher["device_memory"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("device cpu", "phone cpu", "check cpu")):
                action_res = dispatcher["device_cpu"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("device battery", "phone battery", "check battery")):
                action_res = dispatcher["device_battery"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("adb devices", "adb status")):
                action_res = dispatcher["adb_status"].execute({})
                print_success(action_res)
                continue
            elif any(phrase in cmd_lower for phrase in ("device backup", "backup phone", "backup device")):
                action_res = dispatcher["device_backup"].execute({})
                print_success(action_res)
                continue

            if cmd_lower == "voice-setup":
                from nova.voice.speaker import run_speaker_enrollment_wizard as voice_setup_main
                try:
                    voice_setup_main()
                except Exception as e:
                    print_error(f"Voice setup failed: {e}")
                continue
            elif cmd_lower == "voice-reset":
                from nova.voice.speaker import run_speaker_reset_wizard as voice_reset_main
                try:
                    voice_reset_main()
                except Exception as e:
                    print_error(f"Voice reset failed: {e}")
                continue
            elif cmd_lower == "voice-test":
                from nova.voice.pipeline import run_voice_self_test as voice_test_main
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
                print_error("All AI APIs failed (Nebius, Gemini, and Ollama). Check your API keys and network connection.")
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
            
            from nova.ai.planner import Goal
            from nova.ai.reasoning import route_query_to_planner_pipeline
            
            # Check autonomous state to determine if approval is required
            approval_required = not StateManager.is_autonomous()
            
            # Set up goal carrying NLP actions list as metadata for dynamic planners
            goal = Goal(description=user_input)
            goal.metadata = {"actions": actions_list}
            
            try:
                result_message = route_query_to_planner_pipeline(
                    query=user_input,
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
                    emit("task_completed", module="core", status="success" if status == "success" else "failed", metadata={"goal": user_input, "message": result_message, "status_code": status})
                except Exception:
                    pass
                    
                # Save to history
                HistoryManager.add_entry(
                    user_input=user_input,
                    parsed_action={},
                    executed_commands=CommandExecutor.get_last_commands(),
                    status=status,
                    result_message=result_message
                )
            except Exception as e:
                print_error(f"An exception occurred while executing plan: {e}")
                HistoryManager.add_entry(
                    user_input=user_input,
                    parsed_action={},
                    executed_commands=CommandExecutor.get_last_commands(),
                    status="exception_raised"
                )
                
        except KeyboardInterrupt:
            print()
            print_info("Interrupt received. Type 'exit' to quit or continue.")
        except EOFError:
            print()
            print_info("Goodbye!")
            break
        except Exception as e:
            print_error(f"An unexpected error occurred: {e}")
