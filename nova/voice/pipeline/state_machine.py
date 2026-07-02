import time
import threading
import random
import re
from enum import Enum, auto
from nova.logger import logger
from nova.voice.config import (
    SAMPLE_RATE, CHANNELS, wake_word_model_path, wake_word_threshold
)
import nova.voice.config as voice_config
from nova.voice.wakeword import LocalWakeWordDetector

class VoiceState(Enum):
    TEXT_MODE = auto()
    VOICE_IDLE = auto()
    WAKE_DETECTED = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    EXECUTING = auto()
    SPEAKING = auto()
    PUSH_TO_TALK = auto()
    SHUTDOWN = auto()
    INACTIVE = auto()


voice_active_event = threading.Event()
shutdown_event = threading.Event()
_current_state = VoiceState.INACTIVE

_mic_healthy = False
_wake_healthy = False
_stt_healthy = False
_deferred_deactivate = False
_state_lock = threading.Lock()

def set_deferred_deactivate(val: bool) -> None:
    global _deferred_deactivate
    _deferred_deactivate = val

def transition_state(new_state: VoiceState) -> None:
    global _current_state
    with _state_lock:
        _current_state = new_state
    logger.debug(f"[STATE] Transitioned to {new_state.name}")

def get_current_state() -> VoiceState:
    global _current_state
    with _state_lock:
        return _current_state

def get_voice_status_report() -> dict:
    from nova.browser.manager import BrowserManager
    from nova.voice.config import ENABLE_TTS
    
    with _state_lock:
        state_name = _current_state.name if _current_state else "UNKNOWN"
    browser_running = BrowserManager.is_browser_running()
    browser_status = "Healthy (Active)" if browser_running else "Inactive"
    
    mic_status = "Healthy (Open)" if _mic_healthy else "Unavailable"
    wake_status = "Healthy (Ready)" if _wake_healthy else "Unavailable"
    stt_status = "Healthy (Ready)" if _stt_healthy else "Unavailable"
    tts_status = "Healthy (Ready)" if ENABLE_TTS else "Disabled"
    health = "Healthy" if (_mic_healthy and _wake_healthy) else "Degraded"
    
    return {
        "running": True,
        "state": state_name,
        "wake_word": wake_status,
        "whisper": stt_status,
        "elevenlabs": tts_status,
        "browser": browser_status,
        "microphone": mic_status,
        "health": health
    }

def set_health_states(mic: bool = None, wake: bool = None, stt: bool = None):
    global _mic_healthy, _wake_healthy, _stt_healthy
    if mic is not None:
        _mic_healthy = mic
    if wake is not None:
        _wake_healthy = wake
    if stt is not None:
        _stt_healthy = stt

def recover_microphone(old_stream):
    global _mic_healthy
    logger.warning("Microphone error or disconnect detected. Attempting to recover...")
    _mic_healthy = False
    if old_stream is not None:
        try:
            old_stream.stop()
            old_stream.close()
        except Exception:
            pass
    try:
        import sounddevice as sd
    except ImportError:
        logger.error("Failed to import sounddevice during microphone recovery.")
        return None
        
    while not shutdown_event.is_set():
        try:
            if not sd.query_devices(kind="input"):
                raise RuntimeError("No input device available.")
            new_stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32")
            new_stream.start()
            logger.info("Microphone successfully recovered.")
            _mic_healthy = True
            voice_config.active_stream = new_stream
            return new_stream
        except Exception as e:
            logger.debug(f"Microphone recovery failed: {e}. Retrying in 2 seconds...")
            time.sleep(2)
    return None

def recover_wake_detector(old_detector):
    global _wake_healthy
    logger.warning("Wake-word engine issue detected. Attempting to recover...")
    _wake_healthy = False
    while not shutdown_event.is_set():
        try:
            new_detector = LocalWakeWordDetector(
                model_path=wake_word_model_path,
                confidence_threshold=wake_word_threshold,
            )
            logger.info("Wake-word engine successfully recovered.")
            _wake_healthy = True
            return new_detector
        except Exception as e:
            logger.debug(f"Wake-word recovery failed: {e}. Retrying in 2 seconds...")
            time.sleep(2)
    return None

def check_long_running_action(dispatcher, actions: list, user_query: str) -> tuple[bool, str, str, str]:
    long_action = None
    for action_data in actions:
        name = action_data.get("action")
        handler = dispatcher.get(name)
        if handler:
            is_long = False
            if hasattr(handler, "is_long_running") and handler.is_long_running:
                is_long = True
            elif name in ("chromium_action", "browser_action", "search_package", "open_app", "install_package", 
                          "remove_package", "update_package", "git_command", "nix_shell", 
                          "adb_mirroring", "adb_device_op", "search_files", "locate_files"):
                is_long = True
            
            if is_long:
                long_action = action_data
                break
                
    if not long_action:
        return False, "", "", ""
        
    action_name = long_action.get("action", "")
    params = long_action
    user_query_lower = user_query.lower()
    
    subject = ""
    for k in ("app", "query", "search_query", "filename", "url", "package"):
        val = params.get(k)
        if val and isinstance(val, str) and val.strip():
            subject = val.strip()
            break
            
    if not subject:
        for marker in ("play ", "search for ", "search ", "find ", "open ", "launch ", "look for "):
            if marker in user_query_lower:
                idx = user_query_lower.find(marker) + len(marker)
                subject = user_query[idx:].strip().rstrip(".?")
                break

    subject_clean = subject
    if subject_clean.startswith(("http://", "https://")) or (any(ext in subject_clean.lower() for ext in (".com", ".org", ".net", ".io")) and "." in subject_clean):
        domain = subject_clean.replace("http://", "").replace("https://", "")
        if "/" in domain:
            domain = domain.split("/", 1)[0]
        domain = domain.replace("www.", "")
        subject_clean = domain.split(".")[0].capitalize()

    if subject_clean.lower() in ("youtube.com", "google.com", "youtube", "google"):
        for marker in ("play ", "search for ", "search ", "find ", "open ", "launch ", "look for "):
            if marker in user_query_lower:
                idx = user_query_lower.find(marker) + len(marker)
                subject_clean = user_query[idx:].strip().rstrip(".?")
                break

    if subject_clean.lower() == "chatgpt":
        subject_clean = "ChatGPT"

    if "youtube.com" in subject_clean or "youtube" in user_query_lower:
        subject_clean = re.sub(r"\s+on\s+youtube.*", "", subject_clean, flags=re.IGNORECASE).strip()
    
    ack_text = "Working on that."
    success_text = "Done."
    fail_text = "I couldn't complete that request."
    
    if action_name in ("browser_action", "chromium_action"):
        url = params.get("url", "").lower()
        operation = params.get("operation", "").lower()
        if "youtube" in url or "youtube" in user_query_lower or operation == "youtube_search":
            if subject_clean and subject_clean.lower() not in ("youtube", "http", "https"):
                acks = [
                    "Looking for that on YouTube.",
                    f"Searching YouTube for {subject_clean}.",
                    "One moment, finding it on YouTube.",
                    "Let me find that for you on YouTube.",
                    "I'll play that for you."
                ]
                successes = [
                    "Now playing. Enjoy!",
                    "Your music is ready.",
                    "I've started playback.",
                    f"Now playing {subject_clean}."
                ]
                ack_text = random.choice(acks)
                success_text = random.choice(successes)
            else:
                ack_text = "Opening YouTube."
                success_text = "YouTube is open."
            fail_text = "I couldn't find that song."
            
        elif "github" in url or "github" in user_query_lower:
            ack_text = "Opening GitHub."
            success_text = "GitHub is open."
            
        elif "google" in url or "google" in user_query_lower:
            if "search" in user_query_lower or "find" in user_query_lower:
                if subject_clean and subject_clean.lower() not in ("google", "http", "https"):
                    acks = [
                        f"Searching Google for {subject_clean}.",
                        f"Looking that up on Google.",
                        f"Let me search Google for {subject_clean}."
                    ]
                    ack_text = random.choice(acks)
                else:
                    ack_text = "Searching Google."
                success_text = "I found the results."
            else:
                ack_text = "Opening Google."
                success_text = "Google is ready."
        else:
            if subject_clean:
                ack_text = f"Opening {subject_clean}."
                success_text = f"{subject_clean} is ready."
            else:
                ack_text = "Opening the browser."
                success_text = "Browser is ready."
                
    elif action_name == "open_app":
        app = params.get("app", "")
        app_name = subject_clean or app
        if app_name:
            app_cap = app_name[0].upper() + app_name[1:] if app_name else ""
            acks = [
                f"Launching {app_cap}.",
                f"Opening {app_cap}.",
                f"One moment, starting {app_cap}."
            ]
            successes = [
                f"{app_cap} is ready.",
                f"{app_cap} is open."
            ]
            ack_text = random.choice(acks)
            success_text = random.choice(successes)
        else:
            ack_text = "Launching application."
            success_text = "Application is ready."
            
    elif action_name in ("google_search", "web_search", "search_package"):
        if subject_clean:
            acks = [
                f"Searching for {subject_clean}.",
                f"Looking that up.",
                f"Let me search for {subject_clean}."
            ]
            ack_text = random.choice(acks)
        else:
            ack_text = "Searching the web."
        success_text = "I found the results."
        
    elif action_name in ("search_files", "locate_files", "files_action"):
        if subject_clean:
            ack_text = f"Looking for your {subject_clean}."
            success_text = f"I found your {subject_clean}."
        else:
            ack_text = "Looking for your file."
            success_text = "I found your file."
            
    elif action_name in ("install_package", "remove_package", "update_package"):
        pkg = params.get("package", "")
        pkg_name = subject_clean or pkg
        if action_name == "install_package":
            ack_text = f"Installing {pkg_name}." if pkg_name else "Installing package."
            success_text = "Installation complete."
        elif action_name == "remove_package":
            ack_text = f"Uninstalling {pkg_name}." if pkg_name else "Removing package."
            success_text = "Package removed."
        else:
            ack_text = "Updating package."
            success_text = "Update complete."
            
    elif action_name == "git_command":
        ack_text = "Running git command."
        success_text = "Git command complete."
        
    elif action_name == "adb_mirroring":
        ack_text = "Connecting to device mirror..."
        success_text = "Device mirroring is ready."
        
    elif action_name == "adb_device_op":
        ack_text = "Connecting to Android device..."
        success_text = "Device command complete."

    return True, ack_text, success_text, fail_text
