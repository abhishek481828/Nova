"""
Voice Mode — production-quality state machine.

State 1  IDLE     — Nothing open.  Press ENTER to activate.
State 2  WAITING  — Mic open, calibrated, wake-word engine + speaker verifier.
State 3  COMMAND  — Wake phrase heard + speaker verified, recording command.
State 4  → WAITING (auto-return, no recalibration)
EXIT             — All resources released cleanly.

Logging sequence (matches specification):
  Voice Mode Ready
  Voice Mode Activated
  Microphone Opened
  Calibration Complete
  Wake Engine Ready
  Waiting for "Hey Nova"
  Wake Detected
  Listening
  [🛑 Silence detected   — from recorder.py]
  🧠 Transcribing
  ▶ Executing
  ✔ Finished
  Waiting for "Hey Nova"
  Voice Mode Closed
"""

import re
import time
import subprocess
import collections
import numpy as np
import sounddevice as sd
import nova.voice.config as voice_config

from nova.voice.config import (
    SAMPLE_RATE, CHANNELS, VAD_THRESHOLD,
    AMBIENT_CALIBRATION_DURATION, NOISE_FLOOR_MARGIN,
    enable_wake_word, wake_word_phrase, wake_word_model_path,
    wake_word_threshold, confirmation_sound, enable_debug,
    enable_speaker_verification, speaker_similarity_threshold,
    speaker_embedding_path,
)
from nova.voice.speaker_verify import SpeakerVerifier, _RESEMBLYZER_AVAILABLE
from nova.voice.stt import get_stt_provider
from nova.voice.tts import speak
from nova.voice.recorder import record_audio_from_stream
from nova.voice.wake_word import LocalWakeWordDetector
from nova.voice.audio_processor import AudioDiagnostics, select_best_microphone
from nova.voice.adaptive_wake import AdaptiveWakeController
from nova.voice.confidence_fusion import ConfidenceFusionEngine
from nova.voice.audio_quality import AudioQualityAnalyzer
from nova.voice.diagnostics import VoiceDiagnosticsEngine
from nova.logger import logger
from nova.utils import print_info, print_warning, print_error, print_success
from enum import Enum, auto

class VoiceState(Enum):
    TEXT_MODE = auto()          # initial state, awaiting activation
    VOICE_IDLE = auto()         # idle, waiting for "Hey Nova"
    WAKE_DETECTED = auto()      # wake word detected, playing chime / verifying speaker
    LISTENING = auto()          # actively recording user command
    TRANSCRIBING = auto()       # transcribing audio via Faster-Whisper
    EXECUTING = auto()          # parsing intent and dispatching actions
    SPEAKING = auto()           # speaking success response via Edge-TTS
    PUSH_TO_TALK = auto()       # fallback waiting for enter key
    SHUTDOWN = auto()           # cleaning up resources and exiting
    INACTIVE = auto()           # deactivated, microphone released


import threading
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
    from nova.browser_manager import BrowserManager
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

def recover_microphone(old_stream):
    logger.warning("Microphone error or disconnect detected. Attempting to recover...")
    global _mic_healthy
    _mic_healthy = False
    if old_stream is not None:
        try:
            old_stream.stop()
            old_stream.close()
        except Exception:
            pass
    while not shutdown_event.is_set():
        try:
            if not sd.query_devices(kind="input"):
                raise RuntimeError("No input device available.")
            new_stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32"
            )
            new_stream.start()
            logger.info("Microphone successfully recovered.")
            _mic_healthy = True
            import nova.voice.config as voice_config
            voice_config.active_stream = new_stream
            return new_stream
        except Exception as e:
            logger.debug(f"Microphone recovery failed: {e}. Retrying in 2 seconds...")
            time.sleep(2)
    return None

def recover_wake_detector(old_detector):
    logger.warning("Wake-word engine issue detected. Attempting to recover...")
    global _wake_healthy
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



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_ansi(text: str) -> str:
    return re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").sub("", text)


# Phrases that mean "stop what you're doing and listen to me again"
_STOP_PHRASES = frozenset([
    "stop nova", "stop", "cancel", "never mind", "nevermind", "that's enough",
    "thats enough", "be quiet", "shut up", "pause", "wait", "hold on",
    "hey nova", "ok nova", "okay nova", "nova stop", "nova cancel",
])

# Phrases that can be used at the start of a longer sentence to interrupt
_PREFIX_STOP_PHRASES = frozenset([
    "stop nova", "cancel", "never mind", "nevermind", "be quiet", "shut up",
    "hey nova", "ok nova", "okay nova", "nova stop", "nova cancel",
])

def _is_interrupt_phrase(text: str) -> bool:
    """Return True if the transcribed text is a stop/interrupt command."""
    t = text.lower().strip().rstrip(".").rstrip(",")
    if t in _STOP_PHRASES:
        return True
    # Also match if ANY prefix stop phrase appears at the start of the utterance
    for phrase in _PREFIX_STOP_PHRASES:
        if t.startswith(phrase):
            return True
    return False



_interrupt_listener_active = threading.Event()

def _start_background_interrupt_listener(stream, stt_provider, calibrated_threshold: float) -> None:
    """
    Spawns a daemon thread that continuously reads short audio bursts from the
    microphone during SPEAKING / EXECUTING states and checks for interrupt phrases
    ("stop nova", "hey nova", etc.).

    When detected, sets voice_config.interrupt_speaking = True so the TTS
    playback loop stops immediately.
    """
    import nova.voice.config as voice_config

    _interrupt_listener_active.set()

    def _listener():
        import sounddevice as sd
        import numpy as np
        import io, wave
        SAMPLE_RATE = 16000
        CHANNELS = 1
        LISTEN_SECS = 2.0          # record 2s bursts
        SILENCE_GATE = calibrated_threshold * 1.5

        while _interrupt_listener_active.is_set():
            try:
                # Read a short burst from the open stream (B44 / stream_lock)
                n_samples = int(SAMPLE_RATE * LISTEN_SECS)
                with voice_config.stream_lock:
                    if stream is None or not stream.active:
                        break
                    try:
                        raw, _ = stream.read(n_samples)
                    except Exception:
                        break

                flat = raw.flatten()
                rms = float(np.sqrt(np.mean(flat * flat)))
                if rms < SILENCE_GATE:
                    # Pure silence — skip transcription to save CPU
                    continue

                # Convert to 16-bit PCM WAV bytes for STT
                audio_int16 = (np.clip(flat, -1.0, 1.0) * 32767).astype(np.int16)
                wav_io = io.BytesIO()
                with wave.open(wav_io, "wb") as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(2)
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(audio_int16.tobytes())
                wav_bytes = wav_io.getvalue()

                try:
                    heard = stt_provider.transcribe(wav_bytes, silent=True).strip()
                except Exception:
                    continue

                if heard and _is_interrupt_phrase(heard):
                    logger.debug(f"Background interrupt detected: '{heard}'")
                    voice_config.interrupt_speaking = True
                    _interrupt_listener_active.clear()
                    break

            except Exception as e:
                logger.debug(f"Background interrupt listener error: {e}")
                break

    t = threading.Thread(target=_listener, daemon=True)
    t.start()


def _stop_background_interrupt_listener() -> None:
    """Signal the background interrupt listener thread to exit."""
    _interrupt_listener_active.clear()


def play_confirmation_sound() -> None:
    """Short double-chime played immediately after wake detection."""
    try:
        sr = 16000
        t1 = np.linspace(0, 0.08, int(sr * 0.08), endpoint=False)
        t2 = np.linspace(0, 0.12, int(sr * 0.12), endpoint=False)
        tone1 = 0.15 * np.sin(2 * np.pi * 880  * t1)
        tone2 = 0.15 * np.sin(2 * np.pi * 1320 * t2)
        pause = np.zeros(int(sr * 0.02))
        audio = np.concatenate([tone1, pause, tone2])
        fade_len = int(sr * 0.02)
        audio[-fade_len:] *= np.linspace(1.0, 0.0, fade_len)
        sd.play(audio, sr)
        sd.wait()
    except Exception as e:
        logger.debug(f"Confirmation sound failed: {e}")


def get_user_confirmation(prompt: str, stream, speech_threshold) -> bool:
    """Speaks confirmation prompt, listens for yes/no response, and returns True if confirmed."""
    speak(prompt)
    try:
        time.sleep(0.2)
        # Record response
        response_audio = record_audio_from_stream(stream, calibrated_threshold=speech_threshold)
        # Transcribe response
        stt_provider = get_stt_provider()
        response_text = stt_provider.transcribe(response_audio, silent=True).strip().lower()
        logger.debug(f"User confirmation response: '{response_text}'")
        # Check if they said yes or positive words
        positives = ("yes", "yeah", "yep", "sure", "correct", "do it", "play", "open", "go ahead")
        if any(p in response_text for p in positives):
            return True
    except Exception as e:
        logger.debug(f"Confirmation failed: {e}")
    return False


def check_long_running_action(dispatcher, actions: list, user_query: str) -> tuple[bool, str, str, str]:
    """
    Checks if there is a long-running action in the actions list.
    Returns (is_long, ack_text, completion_success_text, completion_fail_text).
    """
    import re
    import random
    
    # 1. Identify the first action that is long-running
    long_action = None
    long_handler = None
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
                long_handler = handler
                break
                
    if not long_action:
        return False, "", "", ""
        
    action_name = long_action.get("action", "")
    params = long_action
    user_query_lower = user_query.lower()
    
    # Extract subject
    subject = ""
    for k in ("app", "query", "search_query", "filename", "url", "package"):
        val = params.get(k)
        if val and isinstance(val, str) and val.strip():
            subject = val.strip()
            break
            
    if not subject:
        # Try parsing from user_query
        for marker in ("play ", "search for ", "search ", "find ", "open ", "launch ", "look for "):
            if marker in user_query_lower:
                idx = user_query_lower.find(marker) + len(marker)
                subject = user_query[idx:].strip().rstrip(".?")
                break

    # Clean up subject if it's a URL
    subject_clean = subject
    if subject_clean.startswith(("http://", "https://")) or (any(ext in subject_clean.lower() for ext in (".com", ".org", ".net", ".io")) and "." in subject_clean):
        domain = subject_clean.replace("http://", "").replace("https://", "")
        if "/" in domain:
            domain = domain.split("/", 1)[0]
        domain = domain.replace("www.", "")
        subject_clean = domain.split(".")[0].capitalize()

    # If the subject is just a generic site, let's try to extract the query subject from user command
    if subject_clean.lower() in ("youtube.com", "google.com", "youtube", "google"):
        for marker in ("play ", "search for ", "search ", "find ", "open ", "launch ", "look for "):
            if marker in user_query_lower:
                idx = user_query_lower.find(marker) + len(marker)
                subject_clean = user_query[idx:].strip().rstrip(".?")
                break

    if subject_clean.lower() == "chatgpt":
        subject_clean = "ChatGPT"

    if "youtube.com" in subject_clean or "youtube" in user_query_lower:
        # Strip "on youtube" suffix
        subject_clean = re.sub(r"\s+on\s+youtube.*", "", subject_clean, flags=re.IGNORECASE).strip()
    
    # Default fallbacks
    ack_text = "Working on that."
    success_text = "Done."
    fail_text = "I couldn't complete that request."
    
    if action_name in ("browser_action", "chromium_action"):
        url = params.get("url", "").lower()
        operation = params.get("operation", "").lower()
        if "youtube" in url or "youtube" in user_query_lower or operation == "youtube_search":
            if subject_clean and subject_clean.lower() not in ("youtube", "http", "https"):
                # YouTube search / playback
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


# ---------------------------------------------------------------------------
# Wake-word loop  (State 2)
# ---------------------------------------------------------------------------

_WAKE_CHUNK   = 480   # 30 ms at 16 kHz — minimum block for VAD / OWW
_WAKE_FRAME   = 1280  # samples required by OpenWakeWord per inference call
_NOISE_GATE   = 2.0   # chunk must be ≥ 2× noise floor to normalise
_TARGET_RMS   = 0.08
_WAKE_COOLDOWN = 1.5  # seconds before a second trigger is accepted


# Seconds of audio to retain before the trigger so the wake phrase itself
# is available for speaker verification ("Hey Nova" ≈ 0.8–1.2 s)
_WAKE_CAPTURE_SECS = 2.0


class CircularAudioBuffer:
    """Pre-allocated circular buffer using numpy to avoid repeated allocations."""
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.buffer = np.zeros(capacity, dtype=np.float32)
        self.index = 0
        self.filled = False

    def extend(self, data: np.ndarray):
        n = len(data)
        if n >= self.capacity:
            self.buffer[:] = data[-self.capacity:]
            self.index = 0
            self.filled = True
            return
        
        end = self.index + n
        if end <= self.capacity:
            self.buffer[self.index:end] = data
            self.index = end
        else:
            first_part = self.capacity - self.index
            self.buffer[self.index:] = data[:first_part]
            self.buffer[:n - first_part] = data[first_part:]
            self.index = n - first_part
            self.filled = True

        if self.index >= self.capacity:
            self.index = 0
            self.filled = True

    def get_latest(self) -> np.ndarray:
        if not self.filled:
            return self.buffer[:self.index].copy()
        return np.concatenate((self.buffer[self.index:], self.buffer[:self.index]))


def _wait_for_wake(
    stream: sd.InputStream,
    wake_detector: "LocalWakeWordDetector",
    noise_floor: float,
) -> tuple[bool, np.ndarray | None, float]:
    """
    Blocking.  Returns (True, wake_audio) when the wake phrase is detected.
    Returns (False, empty_array) only on unrecoverable stream error.

    The returned ``wake_audio`` is the last _WAKE_CAPTURE_SECS of float32
    audio captured during idle listening — used by the speaker verifier.
    """
    # Drain any stale frames that accumulated while we were busy
    try:
        with voice_config.stream_lock:
            if stream.read_available > 0:
                stream.read(stream.read_available)
    except Exception:
        pass

    _cap_len = int(SAMPLE_RATE * _WAKE_CAPTURE_SECS)
    capture_buffer = CircularAudioBuffer(_cap_len)

    # Accumulate raw samples so we can feed OWW in 1280-sample (80 ms) chunks
    # — the exact frame size its internal preprocessor expects.
    oww_accum = np.zeros(0, dtype=np.int16)

    # Software gain applied to mic audio before OWW inference.
    # The hey_nova_v0.1 model scores low (~0.10-0.14) on typical laptop
    # built-in mics at normal gain.  A 2x boost brings the signal closer
    # to the level the model was trained on (diagnostic confirmed 2x is
    # the sweet spot before clipping occurs).
    _SOFTWARE_GAIN = 2.0

    # Detection threshold — the v0.1 model with 2x gain typically scores
    # 0.08-0.18 on laptop mics. A threshold of 0.07 captures the wake word
    # very reliably.
    _DETECT_THRESHOLD = 0.07

    # Trigger immediately on a single frame exceeding the threshold (1-of-1).
    # This maximizes activation responsiveness so it triggers on the first try.
    _PATIENCE = 1
    _PATIENCE_WINDOW = 1
    score_history = collections.deque(maxlen=_PATIENCE_WINDOW)

    last_trigger = 0.0

    while True:
        if shutdown_event.is_set() or _current_state == VoiceState.INACTIVE:
            return False, None, 0.0

        # Check if client signal / keyboard shortcut triggered listening
        if voice_active_event.is_set():
            voice_active_event.clear()
            return True, None, 1.0

        # --- read one 30 ms block (480 samples) from mic ---
        try:
            with voice_config.stream_lock:
                recording, _ = stream.read(_WAKE_CHUNK)
        except Exception as e:
            logger.debug(f"Wake-loop read error: {e}")
            stream = recover_microphone(stream)
            if shutdown_event.is_set() or _current_state == VoiceState.INACTIVE:
                return False, None, 0.0
            continue

        flat = recording.flatten()

        # Apply Acoustic Echo Cancellation if enabled
        aec = getattr(voice_config, "active_aec", None)
        if aec is not None:
            flat = aec.process(flat)

        # Keep raw float32 audio for speaker-verification capture buffer
        capture_buffer.extend(flat)

        # Apply software gain and convert to int16 PCM for OpenWakeWord.
        amplified = flat * _SOFTWARE_GAIN
        pcm_chunk = (np.clip(amplified, -1.0, 1.0) * 32767).astype(np.int16)
        oww_accum = np.concatenate((oww_accum, pcm_chunk))

        # Only run inference once we have a full 1280-sample frame
        # (OpenWakeWord's streaming preprocessor expects non-overlapping
        #  1280-sample chunks; feeding overlapping windows corrupts its
        #  internal mel-spectrogram buffer).
        if len(oww_accum) < _WAKE_FRAME:
            continue

        # Feed exactly 1280 samples and keep any remainder
        oww_frame = oww_accum[:_WAKE_FRAME]
        oww_accum = oww_accum[_WAKE_FRAME:]

        # --- run OpenWakeWord inference ---
        try:
            predictions = wake_detector.model.predict(oww_frame)
        except Exception as e:
            logger.debug(f"OWW inference error: {e}")
            continue

        score = predictions.get(wake_detector.model_name, 0.0)

        # Check rule-based Nova detector using the last 0.5s of float32 audio
        is_nova = False
        try:
            if hasattr(wake_detector, 'nova_detector'):
                latest_audio = capture_buffer.get_latest()
                # Get the last 0.5 seconds (8000 samples at 16kHz)
                if len(latest_audio) >= 8000:
                    is_nova = wake_detector.nova_detector.detect(latest_audio[-8000:], SAMPLE_RATE)
        except Exception as e:
            logger.debug(f"Nova detector failed: {e}")

        # If Nova was detected, set a high score to trigger the wake-up
        if is_nova:
            score = max(score, 0.95)

        score_history.append(score)

        if enable_debug:
            rms_val = float(np.sqrt(np.mean(flat * flat)))
            peak = float(np.max(np.abs(flat)))
            hits = sum(1 for s in score_history if s >= _DETECT_THRESHOLD)
            print(
                f"[DBG wake] score={score:.4f}  "
                f"thresh={_DETECT_THRESHOLD}  "
                f"hits={hits}/{_PATIENCE}  "
                f"rms={rms_val:.4f}  peak={peak:.4f}"
            )

        # Consecutive-frame validation: require _PATIENCE frames above
        # threshold within the last _PATIENCE_WINDOW frames.
        hits = sum(1 for s in score_history if s >= _DETECT_THRESHOLD)
        if hits >= _PATIENCE:
            now = time.time()
            if now - last_trigger < _WAKE_COOLDOWN:
                score_history.clear()
                continue
            last_trigger = now
            score_history.clear()
            wake_audio = capture_buffer.get_latest()
            return True, wake_audio, float(score)   # ← wake detected


# ---------------------------------------------------------------------------
# Main voice loop
# ---------------------------------------------------------------------------

class VoiceLoopState:
    """State context container for Nova's voice loop iterations."""
    def __init__(self, diagnostics=None):
        self.stt_provider = None
        self.verifier = None
        self.stream = None
        self.wake_detector = None
        self.adaptive_wake_ctrl = AdaptiveWakeController()
        self.fusion_engine = ConfidenceFusionEngine()
        self.quality_analyzer = AudioQualityAnalyzer()
        self.diagnostics = diagnostics if diagnostics is not None else VoiceDiagnosticsEngine()
        import nova.voice.config as _vc_cfg
        _vc_cfg.active_diagnostics = self.diagnostics
        self.use_wake_word = enable_wake_word
        self.noise_floor = VAD_THRESHOLD
        self.speech_threshold = VAD_THRESHOLD + NOISE_FLOOR_MARGIN
        self.calibrated = False
        self._greeted_this_activation = False
        self._first_ptt_since_activation = False
        self.last_command_snr = None
        self.last_clipping_pct = None
        self.skip_idle_wait = False
        self.hp_filter = None
        self.rnnoise = None
        self.agc = None
        self.vad = None
        self.aec = None
        self.current_state = VoiceState.INACTIVE
        self.last_printed_state = None


def process_single_iteration(
    state: VoiceLoopState,
    ai_client,
    dispatcher,
    transition_to
) -> str:
    """
    Executes a single wake-detection and command-processing cycle of the voice pipeline.
    
    Returns
    -------
    "continue" - loop should continue to the next iteration
    "break"    - loop should break and perform cleanup
    "menu"     - loop should break and return "menu"
    "exit"     - loop should break and return "exit"
    """
    global _mic_healthy, _wake_healthy, _stt_healthy, _deferred_deactivate

    # Bind local variables from state container
    stt_provider = state.stt_provider
    verifier = state.verifier
    stream = state.stream
    wake_detector = state.wake_detector
    adaptive_wake_ctrl = state.adaptive_wake_ctrl
    fusion_engine = state.fusion_engine
    quality_analyzer = state.quality_analyzer
    diagnostics = state.diagnostics
    use_wake_word = state.use_wake_word
    noise_floor = state.noise_floor
    speech_threshold = state.speech_threshold
    calibrated = state.calibrated
    _greeted_this_activation = state._greeted_this_activation
    _first_ptt_since_activation = state._first_ptt_since_activation
    last_command_snr = state.last_command_snr
    last_clipping_pct = state.last_clipping_pct
    skip_idle_wait = state.skip_idle_wait
    hp_filter = state.hp_filter
    rnnoise = state.rnnoise
    agc = state.agc
    vad = state.vad
    aec = state.aec
    last_printed_state = state.last_printed_state

    from nova.voice.audio_processor import AmbientCalibrator

    def save_state():
        state.stt_provider = stt_provider
        state.verifier = verifier
        state.stream = stream
        state.wake_detector = wake_detector
        state.noise_floor = noise_floor
        state.speech_threshold = speech_threshold
        state.calibrated = calibrated
        state._greeted_this_activation = _greeted_this_activation
        state._first_ptt_since_activation = _first_ptt_since_activation
        state.last_command_snr = last_command_snr
        state.last_clipping_pct = last_clipping_pct
        state.skip_idle_wait = skip_idle_wait
        state.hp_filter = hp_filter
        state.rnnoise = rnnoise
        state.agc = agc
        state.vad = vad
        state.aec = aec
        state.last_printed_state = last_printed_state

    # Reset explicit state variables for each turn iteration
    quality_metrics = None
    speaker_score = None
    cmd_start = time.time()

    # Handle Inactive State (release microphone and sleep)
    if _current_state in (VoiceState.INACTIVE, VoiceState.TEXT_MODE):
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            stream = None
            voice_config.active_stream = None
            _mic_healthy = False
        _greeted_this_activation = False
        _first_ptt_since_activation = True  # next PTT activation is the first
        
        while _current_state in (VoiceState.INACTIVE, VoiceState.TEXT_MODE) and not shutdown_event.is_set():
            if voice_active_event.is_set():
                voice_active_event.clear()
                transition_to(VoiceState.VOICE_IDLE)
                break
            time.sleep(0.1)
        save_state()
        return "continue"

    # Lazily initialize voice loop components on activation
    if _current_state == VoiceState.VOICE_IDLE:
        # 1. Load STT Provider
        if stt_provider is None:
            try:
                stt_provider = get_stt_provider()
                _stt_healthy = True
            except Exception as e:
                logger.error(f"Failed to initialize STT provider: {e}")
                _stt_healthy = False
                stt_provider = None

        # 2. Load Speaker Verifier
        if verifier is None and enable_speaker_verification:
            verifier = SpeakerVerifier(
                embedding_path=speaker_embedding_path,
                threshold=speaker_similarity_threshold,
            )
            if not _RESEMBLYZER_AVAILABLE:
                print_warning("resemblyzer not installed — speaker verification disabled.")
                verifier = None
            elif not verifier.has_profile():
                print_warning('No enrolled voice profile found. Using wake-word only. Run "nova voice-setup" to enroll.')
                verifier = None

        # 3. Load Microphone stream
        if stream is None:
            try:
                if not sd.query_devices(kind="input"):
                    raise RuntimeError("No input device found.")
                stream = sd.InputStream(
                    samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32"
                )
                stream.start()
                _mic_healthy = True
                voice_config.active_stream = stream
            except Exception as e:
                print_error(f"Failed to open microphone: {e}")
                _mic_healthy = False
                transition_to(VoiceState.INACTIVE)
                save_state()
                return "continue"

        # 4. Calibrate ambient noise floor
        if not calibrated:
            try:
                calib_n = int(SAMPLE_RATE * AMBIENT_CALIBRATION_DURATION)
                with voice_config.stream_lock:
                    calib_audio, _ = stream.read(calib_n)
                calibrator = AmbientCalibrator()
                calibrator.calibrate(calib_audio)
                noise_floor = calibrator.noise_floor
                speech_threshold = calibrator.speech_threshold
                if noise_floor > 0.5:
                    speech_threshold = 0.02
                calibrated = True
            except Exception as e:
                logger.debug(f"Calibration error: {e}")
                print_warning("Calibration failed — using defaults.")
                calibrated = True

        # 4b. Initialize persistent audio preprocessors (B13)
        if hp_filter is None:
            try:
                from nova.voice.audio_processor import HighPassFilter, RNNoiseWrapper, AutomaticGainControl, WebRTCVoiceActivityDetector, AecProcessor
                from nova.voice.config import ENABLE_HIGHPASS_FILTER, ENABLE_NOISE_SUPPRESSION, ENABLE_AGC, ENABLE_VAD, ENABLE_ECHO_CANCEL, HIGHPASS_CUTOFF, VAD_AGGRESSIVENESS
                
                aec = AecProcessor() if ENABLE_ECHO_CANCEL else None
                voice_config.active_aec = aec

                hp_filter = HighPassFilter(cutoff=HIGHPASS_CUTOFF, fs=SAMPLE_RATE) if ENABLE_HIGHPASS_FILTER else None
                rnnoise = RNNoiseWrapper() if ENABLE_NOISE_SUPPRESSION else None
                agc = AutomaticGainControl() if ENABLE_AGC else None
                vad = WebRTCVoiceActivityDetector(aggressiveness=VAD_AGGRESSIVENESS, default_threshold=speech_threshold) if ENABLE_VAD else None
            except Exception as e:
                logger.debug(f"Failed to initialize persistent preprocessors: {e}")

        # 5. Load wake-word detector
        use_wake_word = enable_wake_word
        if wake_detector is None and use_wake_word:
            try:
                wake_detector = LocalWakeWordDetector(
                    model_path=wake_word_model_path,
                    confidence_threshold=wake_word_threshold,
                )
                _wake_healthy = True
                voice_config.active_wake_detector = wake_detector
            except Exception as e:
                logger.debug(f"Wake-engine load error: {e}")
                _wake_healthy = False
                use_wake_word = False

        # Speak activation greeting (once per activation cycle)
        if not _greeted_this_activation:
            _greeted_this_activation = True
            try:
                from nova.voice.greeting import get_activation_greeting
                greeting_text = get_activation_greeting()
                speak(greeting_text)
                # Flush mic buffer so the greeting audio doesn't trigger wake detection
                time.sleep(0.3)
                if stream is not None:
                    with voice_config.stream_lock:
                        if stream.read_available > 0:
                            stream.read(stream.read_available)
            except Exception:
                pass

    # -----------------------------------------------------------------
    # STATE: VOICE_IDLE or PUSH_TO_TALK
    # -----------------------------------------------------------------
    if not skip_idle_wait:
        if verifier is not None:
            verifier.clear_pending_adaptation()
        
        # Apply dynamic environmental threshold adaptation
        try:
            adapted = adaptive_wake_ctrl.adapt(
                noise_floor,
                signal_quality_snr=last_command_snr,
                clipping_pct=last_clipping_pct
            )
            if wake_detector is not None:
                wake_detector.confidence_threshold = adapted["wake_threshold"]
            if verifier is not None:
                verifier._threshold = adapted["speaker_threshold"]
        except Exception as adapt_err:
            logger.debug(f"Threshold adaptation error: {adapt_err}")

        if use_wake_word:
            transition_to(VoiceState.VOICE_IDLE)
            if last_printed_state != VoiceState.VOICE_IDLE:
                print_info(f'👂 Waiting for "{wake_word_phrase}"')
                last_printed_state = VoiceState.VOICE_IDLE
            detected, wake_audio, wake_score = _wait_for_wake(stream, wake_detector, noise_floor)
            if _current_state == VoiceState.INACTIVE:
                save_state()
                return "continue"
            if not detected:
                if shutdown_event.is_set():
                    save_state()
                    return "break"
                # stream read error — safe to retry
                save_state()
                return "continue"

            # Publish Wake Detected to Dashboard (Robust exception protection)
            try:
                try:
                    from nova.dashboard.event_bus import emit
                    emit("wake_word_detected", module="voice", status="success", metadata={"detector": "OpenWakeWord"})
                except Exception:
                    pass

                # ── Confidence Fusion Engine & Audio Quality Analysis ─────
                transition_to(VoiceState.WAKE_DETECTED)
                if wake_audio is not None:
                    # 1. Analyze audio quality of the wake trigger audio
                    quality_metrics = quality_analyzer.analyze(wake_audio)
                    
                    # 2. Compute VAD speech ratio in the wake audio
                    vad_frames = 0
                    total_frames = len(wake_audio) // 480
                    if total_frames > 0 and vad is not None:
                        for i in range(total_frames):
                            chunk = wake_audio[i*480 : (i+1)*480]
                            if vad.is_speech(chunk, SAMPLE_RATE):
                                vad_frames += 1
                        vad_score = vad_frames / total_frames
                    else:
                        vad_score = None
                        
                    # 3. Get speaker verification score
                    speaker_score = None
                    if verifier is not None:
                        _, speaker_score = verifier.verify(wake_audio, SAMPLE_RATE)
                        
                    # 4. Fuse scores
                    fused_score = fusion_engine.fuse(
                        wake_score=wake_score,
                        speaker_score=speaker_score,
                        vad_score=vad_score,
                        audio_quality=quality_metrics["overall_quality"],
                        noise_level=quality_metrics["background_noise"]
                    )
                    
                    if enable_debug:
                        logger.debug(
                            f"[FUSION] wake={wake_score:.3f} speaker={str(speaker_score)} "
                            f"vad={str(vad_score)} quality={quality_metrics['overall_quality']:.3f} "
                            f"noise={quality_metrics['background_noise']:.5f} -> fused={fused_score:.3f}"
                        )
                        print_info(f"Fused confidence score: {fused_score:.3f}")
                        
                    # 5. Check trigger decision threshold
                    fusion_threshold = getattr(voice_config, "FUSION_TRIGGER_THRESHOLD", 0.50)
                    if fused_score < fusion_threshold:
                        print_warning(
                            f"Trigger rejected by Confidence Fusion Engine (score {fused_score:.2f} < {fusion_threshold}) — continuing to listen."
                        )
                        try:
                            wake_detector.log_false_wake(wake_detector.model_name, wake_score, quality_metrics["background_noise"])
                        except Exception:
                            pass
                        diagnostics.record_false_wake(wake_score, quality_metrics["background_noise"])
                        diagnostics.record_audio_quality(quality_metrics)
                        save_state()
                        return "continue"

                    # Record successful wake trigger with true latency
                    speech_start_t = getattr(wake_detector, "last_speech_start_time_abs", None)
                    if speech_start_t is not None:
                        wake_latency_ms = (time.time() - speech_start_t) * 1000.0
                    else:
                        wake_latency_ms = 800.0  # standard fallback
                        if hasattr(wake_detector, "diagnostics_history") and wake_detector.diagnostics_history:
                            last_diag = wake_detector.diagnostics_history[-1]
                            if last_diag.get("event") == "wake_trigger":
                                wake_latency_ms = last_diag.get("speaking_latency_ms", 800.0)
                    
                    diagnostics.record_wake_success(
                        score=wake_score,
                        latency_ms=wake_latency_ms,
                    )
                    diagnostics.record_audio_quality(quality_metrics)
                    diagnostics.record_noise_sample(quality_metrics["background_noise"])
                # ─────────────────────────────────────────────────────────────

                if enable_debug:
                    print_success("Wake Detected")

                if confirmation_sound:
                    play_confirmation_sound()
                    time.sleep(0.15)

                # Flush chime tail from mic buffer
                try:
                    with voice_config.stream_lock:
                        if stream.read_available > 0:
                            stream.read(stream.read_available)
                except Exception:
                    pass
            except Exception as wake_err:
                import traceback
                logger.error(f"Unrecoverable exception in wake processing: {wake_err}")
                logger.error(traceback.format_exc())
                try:
                    diagnostics.record_missed_wake(wake_score=wake_score, noise_floor=noise_floor)
                except Exception:
                    pass
                transition_to(VoiceState.VOICE_IDLE)
                save_state()
                return "continue"

        else:
            # Push-to-Talk fallback (no wake engine)
            transition_to(VoiceState.PUSH_TO_TALK)
            try:
                input("Press ENTER to record a command...")
            except KeyboardInterrupt:
                save_state()
                return "break"
            except EOFError:
                # Running as a daemon with no TTY — stdin is closed.
                # The keyboard shortcut (Ctrl+Alt+Space) IS the trigger:
                #   - First press: activates voice (consumed in INACTIVE handler)
                #     → proceed immediately to LISTENING (one-press behavior)
                #   - Subsequent presses: wait for voice_active_event signal
                logger.debug("PTT: No TTY detected — daemon mode, shortcut is the trigger.")
                if _first_ptt_since_activation:
                    # First activation via shortcut — go straight to LISTENING
                    _first_ptt_since_activation = False
                else:
                    # Subsequent recordings — wait for next shortcut press
                    while not shutdown_event.is_set() and _current_state not in (VoiceState.INACTIVE, VoiceState.TEXT_MODE):
                        if voice_active_event.is_set():
                            voice_active_event.clear()
                            break  # shortcut pressed → fall through to LISTENING
                        time.sleep(0.1)
                    else:
                        # shutdown or deactivated — exit the outer voice loop
                        save_state()
                        return "break"
                # Fall through to LISTENING
    else:
        skip_idle_wait = False

    # -----------------------------------------------------------------
    # STATE: LISTENING — record user speech command
    # -----------------------------------------------------------------
    transition_to(VoiceState.LISTENING)
    if last_printed_state != VoiceState.LISTENING:
        print_info("🎤 Listening...")
        last_printed_state = VoiceState.LISTENING
        
    # Publish Speech Started to Dashboard
    try:
        from nova.dashboard.event_bus import emit
        emit("speech_started", module="voice", status="running")
    except Exception:
        pass
        
    cmd_start   = time.time()
    record_start = time.time()

    # Mute speakers while we record (prevents mic pickup of playback)
    muted = False
    try:
        subprocess.run(
            ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        muted = True
    except Exception:
        pass

    command_wav = None
    try:
        command_wav = record_audio_from_stream(
            stream, calibrated_threshold=speech_threshold,
            hp_filter=hp_filter, rnnoise=rnnoise, agc=agc, vad=vad,
            aec=aec
        )
    except Exception as e:
        print_error(f"Recording failed: {e}")
    finally:
        if muted:
            try:
                subprocess.run(
                    ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    if command_wav is None:
        # Recording failed — go back to WAITING
        try:
            from nova.dashboard.event_bus import emit
            emit("speech_finished", module="voice", status="failed", metadata={"reason": "recording_failed"})
        except Exception:
            pass
        save_state()
        return "continue"

    record_dur = time.time() - record_start
    
    # Publish Speech Finished to Dashboard
    try:
        from nova.dashboard.event_bus import emit
        emit("speech_finished", module="voice", status="success", metadata={"duration": record_dur})
    except Exception:
        pass

    # Measure audio quality diagnostics on the captured command
    if isinstance(command_wav, bytes):
        try:
            import io as _io, wave as _wave
            with _wave.open(_io.BytesIO(command_wav), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            import numpy as _np
            samples = _np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            diag = AudioDiagnostics(SAMPLE_RATE)
            m = diag.measure(samples)
            last_command_snr = m.get('snr_db', None)
            last_clipping_pct = m.get('clipping_pct', None)
            if enable_debug:
                print(
                    f"[DBG rec] dur={record_dur:.2f}s  "
                    f"rms={m.get('rms',0):.4f}  peak={m.get('peak',0):.4f}  "
                    f"clip={m.get('clipping_pct',0):.2f}%  "
                    f"snr={m.get('snr_db',0):.1f}dB  "
                    f"speech={m.get('speech_dur_s',0):.2f}s"
                )
        except Exception as diag_err:
            logger.debug(f"Diagnostics measurement failed: {diag_err}")

    # -----------------------------------------------------------------
    # STATE: TRANSCRIBING — Whisper speech recognition
    # -----------------------------------------------------------------
    transition_to(VoiceState.TRANSCRIBING)
    if enable_debug:
        print_info("🧠 Transcribing")

    # Publish Transcription Partial to Dashboard
    try:
        from nova.dashboard.event_bus import emit
        emit("transcription_partial", module="stt", status="running")
    except Exception:
        pass

    t0 = time.time()
    try:
        text = stt_provider.transcribe(command_wav, silent=True)
        _stt_healthy = True
    except Exception as e:
        print_error(f"Transcription failed: {e}")
        
        # Publish Transcription Failed to Dashboard
        try:
            from nova.dashboard.event_bus import emit
            emit("transcription_complete", module="stt", status="failed", metadata={"error": str(e)})
        except Exception:
            pass

        logger.warning(f"STT failed: {e}. Re-initializing STT provider...")
        try:
            stt_provider = get_stt_provider()
            _stt_healthy = True
        except Exception as stt_err:
            logger.error(f"Failed to re-initialize STT provider: {stt_err}")
            _stt_healthy = False
        save_state()
        return "continue"
    transcribe_dur = time.time() - t0

    if not text:
        print_warning("I didn't catch that.")
        last_printed_state = VoiceState.VOICE_IDLE
        if use_wake_word and wake_detector is not None:
            try:
                wake_detector.log_false_wake(wake_detector.model_name, 1.0, noise_floor)
            except Exception:
                pass
        save_state()
        return "continue"

    print_success(f'Heard: "{text}"')

    # exit-phrase shortcut
    if text.lower().strip().rstrip(".") in ("exit", "quit", "goodbye"):
        transition_to(VoiceState.SPEAKING)
        speak("Goodbye!")
        save_state()
        return "break"

    # ── Stop / interrupt phrase detection ──────────────────────────────
    if _is_interrupt_phrase(text):
        print_info("🛑 Stop command heard — going back to listening.")
        transition_to(VoiceState.SPEAKING)
        speak("Sure, I'm listening.")
        last_printed_state = VoiceState.VOICE_IDLE
        if confirmation_sound:
            play_confirmation_sound()
        skip_idle_wait = True
        save_state()
        return "continue"

    # -----------------------------------------------------------------
    # STATE: EXECUTING — parsing intent and dispatching actions
    # -----------------------------------------------------------------
    transition_to(VoiceState.EXECUTING)
    if last_printed_state != VoiceState.EXECUTING:
        print_info("▶ Executing...")
        last_printed_state = VoiceState.EXECUTING

    from nova.executor import CommandExecutor
    CommandExecutor.clear_last_commands()

    from nova.spelling import correct_query_spelling, correct_action_data
    import nova.spelling as spelling
    corrected = correct_query_spelling(text)

    # Publish Transcription Complete to Dashboard
    try:
        from nova.dashboard.event_bus import emit
        emit("transcription_complete", module="stt", status="success", metadata={"raw_text": text, "corrected_text": corrected})
    except Exception:
        pass

    # Check for low-confidence transcription or major spelling corrections
    requires_confirm = False
    confirm_prompt = ""

    # 1. Check Whisper logprob (unsure transcription)
    if hasattr(stt_provider, "last_avg_logprob") and stt_provider.last_avg_logprob < -0.85:
        requires_confirm = True
        confirm_prompt = f"Did you mean '{corrected}'?"

    # 2. Check spelling phrase corrections
    if spelling.last_correction_applied:
        try:
            from nova.dashboard.event_bus import emit
            emit("memory_indexed", module="memory", status="success", metadata={
                "action": "spelling_correction",
                "raw_query": text,
                "corrected_query": corrected,
                "prompt": spelling.correction_prompt
            })
        except Exception:
            pass
        requires_confirm = True
        confirm_prompt = spelling.correction_prompt

    if requires_confirm and confirm_prompt:
        confirmed = get_user_confirmation(confirm_prompt, stream, speech_threshold)
        if not confirmed:
            speak("Cancelled.")
            last_printed_state = VoiceState.VOICE_IDLE
            save_state()
            return "continue"

    # Publish LLM Started to Dashboard
    try:
        from nova.dashboard.event_bus import emit
        emit("llm_started", module="llm", status="running", metadata={"query": corrected})
    except Exception:
        pass

    try:
        raw_response = ai_client.parse_intent(corrected)
        
        # Publish LLM Finished to Dashboard
        try:
            from nova.dashboard.event_bus import emit
            emit("llm_finished", module="llm", status="success", metadata={"query": corrected, "response": raw_response})
        except Exception:
            pass
    except Exception as e:
        print_error(f"Intent parsing failed: {e}")
        
        # Publish LLM Failed to Dashboard
        try:
            from nova.dashboard.event_bus import emit
            emit("llm_finished", module="llm", status="failed", metadata={"query": corrected, "error": str(e)})
        except Exception:
            pass
        save_state()
        return "continue"

    if not raw_response:
        print_error("No response from AI — is Ollama running?")
        save_state()
        return "continue"

    from nova.parser import parse_and_validate_action
    try:
        actions = parse_and_validate_action(raw_response)
    except Exception as e:
        print_error(f"Action validation failed: {e}")
        save_state()
        return "continue"

    if not actions:
        print_error("Could not parse an action from the AI response.")
        save_state()
        return "continue"

    success_msgs = []
    
    # Check if there is a long-running action
    is_long, ack_text, success_text, fail_text = check_long_running_action(dispatcher, actions, text)
    
    ack_thread = None
    if is_long:
        import threading
        # Start acknowledgement speech in a non-blocking background thread
        ack_thread = threading.Thread(target=speak, args=(ack_text,))
        ack_thread.start()

    # Start background interrupt listener so "stop nova" / "hey nova"
    # during execution or speaking interrupts Nova immediately.
    _stop_background_interrupt_listener()
    if stt_provider is not None and stream is not None:
        _start_background_interrupt_listener(stream, stt_provider, speech_threshold)

    for action_data in actions:
        action_data = correct_action_data(action_data, corrected)
        name    = action_data.get("action")
        handler = dispatcher.get(name)
        if not handler:
            print_error(f"No handler registered for '{name}'.")
            continue
        if enable_debug:
            print_info(f"Action parsed: {name}")
        try:
            result = handler.execute(action_data)
        except Exception as e:
            print_error(f"Handler '{name}' raised: {e}")
            continue
        lresult = result.lower()
        if "error" in lresult or "failed" in lresult:
            print_error(result)
        elif "aborted" in lresult or "cancelled" in lresult:
            print_warning(result)
        else:
            print_success(result)
            success_msgs.append(result)

    # Commit pending speaker verification voice learning on success
    if verifier is not None:
        verifier.commit_adaptation()

    total_dur = time.time() - cmd_start
    logger.info(
        f"Record: {record_dur:.2f}s | "
        f"Transcribe: {transcribe_dur:.2f}s | "
        f"Total: {total_dur:.2f}s"
    )
    if enable_debug:
        print(
            f"[DBG lat] record={record_dur:.2f}s  "
            f"whisper={transcribe_dur:.2f}s  "
            f"total={total_dur:.2f}s"
        )

    # Once execution finishes, wait for acknowledgement speech to finish playing (with 2s timeout to prevent hang)
    if ack_thread:
        ack_thread.join(timeout=2.0)

    # Measure TTS speaking latency
    _turn_tts_ms = 0.0
    if is_long:
        if success_msgs:
            transition_to(VoiceState.SPEAKING)
            last_printed_state = VoiceState.SPEAKING
            _tts_start = time.perf_counter()
            speak(success_text)
            _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0
        else:
            transition_to(VoiceState.SPEAKING)
            last_printed_state = VoiceState.SPEAKING
            _tts_start = time.perf_counter()
            speak(fail_text)
            _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0
    else:
        if success_msgs:
            transition_to(VoiceState.SPEAKING)
            last_printed_state = VoiceState.SPEAKING
            spoken = " ".join(clean_ansi(m) for m in success_msgs)
            
            # Check if the user explicitly asked to read the full response
            user_text_lower = text.lower()
            read_full_phrases = [
                "read everything", "read the full response", "read the complete response", 
                "read full response", "read all", "read full text", "read the full text"
            ]
            read_full = any(phrase in user_text_lower for phrase in read_full_phrases)
            
            if read_full:
                _tts_start = time.perf_counter()
                speak(spoken)
                _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0
            else:
                try:
                    spoken_summary = ai_client.generate_tts_summary(text, spoken)
                except Exception as e:
                    logger.debug(f"Failed to generate spoken summary: {e}")
                    spoken_summary = spoken
                _tts_start = time.perf_counter()
                speak(spoken_summary)
                _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0

    if enable_debug:
        print_success("✔ Finished")

    # ── Record completed turn diagnostics ─────────────────────────
    try:
        _turn_e2e_ms = (time.time() - cmd_start) * 1000.0
        _turn_stt_ms = transcribe_dur * 1000.0
        _turn_quality = quality_metrics.get("overall_quality", 1.0) if quality_metrics is not None else 1.0
        _turn_noise   = quality_metrics.get("background_noise", 0.0) if quality_metrics is not None else 0.0
        _turn_speaker = float(speaker_score) if speaker_score is not None else None
        diagnostics.record_turn(
            latency_ms=_turn_e2e_ms,
            stt_latency_ms=_turn_stt_ms,
            tts_latency_ms=_turn_tts_ms,
            audio_quality=_turn_quality,
            speaker_confidence=_turn_speaker,
            noise_floor=_turn_noise,
        )
    except Exception as _diag_err:
        logger.debug(f"Diagnostics record_turn failed: {_diag_err}")

    # Stop background interrupt listener
    _stop_background_interrupt_listener()

    # Check if speaking/execution was interrupted
    if voice_config.interrupt_speaking:
        voice_config.interrupt_speaking = False
        print_success("Nova interrupted. Listening...")
        if confirmation_sound:
            play_confirmation_sound()
        skip_idle_wait = True
        save_state()
        return "continue"

    # Flush mic buffer
    try:
        time.sleep(0.8)
        if stream is not None:
            with voice_config.stream_lock:
                if stream.read_available > 0:
                    stream.read(stream.read_available)
    except Exception:
        pass

    # Check if deferred deactivation was flagged
    if _deferred_deactivate:
        _deferred_deactivate = False
        print_info("Nova has stopped listening.")
        transition_to(VoiceState.INACTIVE)

    save_state()
    return "continue"


def run_voice_loop(ai_client, dispatcher, interactive=False) -> str:
    """
    Voice Mode state machine.

    Returns
    -------
    "menu"  — return to the mode-selection menu
    "exit"  — quit Nova entirely
    """
    global _mic_healthy, _wake_healthy, _stt_healthy, _deferred_deactivate

    state = VoiceLoopState()

    def transition_to(new_state: VoiceState, detail: str = ""):
        state.current_state = new_state
        global _current_state
        _current_state = new_state
        logger.debug(f"[STATE] Transitioned to {new_state.name}{f' ({detail})' if detail else ''}")
        try:
            from nova.dashboard.event_bus import emit
            emit("voice_state_change", module="voice", status="running", metadata={"state": new_state.name, "detail": detail})
        except Exception:
            pass

    # =========================================================================
    # Initial state — daemon starts INACTIVE, waiting for toggle
    # =========================================================================
    if interactive:
        transition_to(VoiceState.VOICE_IDLE)
    else:
        transition_to(VoiceState.INACTIVE)
    print_success("Voice Mode Ready")

    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    try:
        while True:
            if shutdown_event.is_set():
                break

            action = process_single_iteration(state, ai_client, dispatcher, transition_to)
            if action == "break":
                break
            elif action == "continue":
                continue
            elif action in ("menu", "exit"):
                return action

    except KeyboardInterrupt:
        print()

    # =========================================================================
    # STATE: SHUTDOWN — exit, release all resources
    # =========================================================================
    transition_to(VoiceState.SHUTDOWN)
    _mic_healthy = False

    # Flush diagnostics to disk on clean shutdown
    try:
        state.diagnostics.flush_to_disk()
    except Exception:
        pass

    if state.stream is not None:
        try:
            state.stream.stop()
            state.stream.close()
        except Exception:
            pass
        import nova.voice.config as voice_config
        voice_config.active_stream = None

    if state.rnnoise:
        try:
            state.rnnoise.destroy()
        except Exception:
            pass

    if state.aec:
        try:
            state.aec.destroy()
        except Exception:
            pass

    print_info("Voice Mode Closed")
    return "menu"
