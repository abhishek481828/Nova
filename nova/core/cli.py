import sys
import os
from nova.ai.ollama import OllamaClient
from nova.parser import parse_and_validate_action
from nova.actions import get_action_dispatcher
from nova.core.executor import CommandExecutor
from nova.core.memory import HistoryManager, WorkingMemory
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
    wm = WorkingMemory()
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
