import time
import threading
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
