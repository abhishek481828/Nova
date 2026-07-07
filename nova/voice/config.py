import os
import tempfile
import threading
try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env", override=True)
except ImportError:
    pass

def get_env(name: str, default: str) -> str:
    # Check NOVA_ prefixed environment variable first, then name.
    nova_name = name if name.startswith("NOVA_") else f"NOVA_{name}"
    unprefixed_name = name.replace("NOVA_", "")
    return os.environ.get(nova_name, os.environ.get(unprefixed_name, default))

ENABLE_VOICE = True
ENABLE_TTS = True

# Preprocessing Pipeline Toggles
ENABLE_NOISE_SUPPRESSION = True   # RNNoise neural denoiser
ENABLE_HIGHPASS_FILTER = True     # Butterworth high-pass (removes fan hum / AC noise)
ENABLE_AGC = True                 # Automatic Gain Control
ENABLE_VAD = True                 # WebRTC Voice Activity Detection
ENABLE_DC_OFFSET_REMOVAL = True   # Subtract mean to remove microphone DC bias
ENABLE_ECHO_CANCEL = get_env("ENABLE_ECHO_CANCEL", "True").lower() == "true"

# Block / Frame Sizes (samples)
BLOCK_SIZE  = 480   # 30 ms at 16 kHz — required minimum for WebRTC VAD and RNNoise
FRAME_SIZE  = 1280  # 80 ms at 16 kHz — OpenWakeWord inference window

# AGC Tuning
AGC_TARGET_RMS = 0.08    # Target RMS level after gain; chosen to keep headroom before clipping
AGC_MAX_GAIN   = 8.0     # Hard ceiling on gain factor to prevent saturation on very quiet mics
AGC_RATE       = 0.05    # Smoothing coefficient (lower = slower, gentler transitions)

# Preprocessing Pipeline Configs
VAD_AGGRESSIVENESS = 2            # Aggressiveness level for WebRTC VAD (0, 1, 2, or 3)
AMBIENT_CALIBRATION_DURATION = 2.0 # Calibration recording length in seconds
FRAME_DURATION = 0.03             # Frame duration in seconds (30ms required for VAD/RNNoise)
NOISE_FLOOR_MARGIN = 0.0005        # Added threshold margin above noise floor
HIGHPASS_CUTOFF = 80.0            # Cutoff frequency for highpass filter in Hz

# Audio Recording Configs
SAMPLE_RATE = 16000        # 16kHz standard for Speech-to-Text
CHANNELS = 1               # Mono audio
RECORDING_TIMEOUT = 20.0   # Maximum length of recording in seconds
SILENCE_TIMEOUT = 2.0      # Stop recording after 2 seconds of silence
# Secure user-private temp directory for temporary voice recordings (S2)
_user_temp_dir = os.path.expanduser("~/.config/nova/tmp")
try:
    os.makedirs(_user_temp_dir, mode=0o700, exist_ok=True)
except Exception:
    _user_temp_dir = tempfile.gettempdir()

TEMP_AUDIO_DIR = get_env("NOVA_TEMP_AUDIO_DIR", _user_temp_dir)


# VAD (Voice Activity Detection) Configs
VAD_THRESHOLD = 0.001      # Root Mean Square (RMS) energy threshold to detect voice activity

# Wake Word Configs
WAKE_WORD = "nova"
WAKE_WORD_CONFIDENCE = 0.5 # Threshold for local wake word match
WAKE_WORD_BUFFER_DURATION = 2.0 # Passive listening buffer duration in seconds
WAKE_WORD_CHECK_INTERVAL = 0.8  # Passive listening evaluation interval in seconds

# OpenWakeWord Configs
enable_wake_word = True
wake_word_phrase = "Hey Nova"

# Confidence Fusion Engine Weights
FUSION_WEIGHT_WAKE = 0.40
FUSION_WEIGHT_SPEAKER = 0.30
FUSION_WEIGHT_VAD = 0.15
FUSION_WEIGHT_QUALITY = 0.10
FUSION_WEIGHT_NOISE = 0.05

# Speaker Verification Continuous Learning
ENABLE_SPEAKER_CONTINUOUS_LEARNING = True
SPEAKER_DRIFT_THRESHOLD = 0.70

# Resolve built-in model path dynamically inside the virtual environment
_default_model_path = ""
try:
    import openwakeword
    _default_model_path = os.path.join(
        os.path.dirname(openwakeword.__file__),
        "resources",
        "models",
        "hey_nova_v0.1.onnx"
    )
except Exception:
    # Fallback to older hardcoded path structure if import fails
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(os.path.dirname(_current_dir))
    _default_model_path = os.path.join(
        _project_root,
        ".venv/lib/python3.12/site-packages/openwakeword/resources/models/hey_nova_v0.1.onnx"
    )

wake_word_model_path = get_env("NOVA_WAKE_WORD_MODEL_PATH", _default_model_path)
wake_word_threshold = float(get_env("NOVA_WAKE_THRESHOLD", "0.3"))
confirmation_sound = True

ENABLE_WAKE_WORD = enable_wake_word
WAKE_WORD_PHRASE = wake_word_phrase
WAKE_WORD_MODEL_PATH = wake_word_model_path
WAKE_WORD_THRESHOLD = wake_word_threshold
CONFIRMATION_SOUND = confirmation_sound
ENABLE_CONFIRMATION_CHIME = get_env("ENABLE_CONFIRMATION_CHIME", "True").lower() == "true"

# Debug Mode — set NOVA_DEBUG=true to enable verbose per-chunk audio logging
enable_debug = get_env("NOVA_DEBUG", "false").lower() == "true"
ENABLE_DEBUG = enable_debug

# Voice Debug Mode — set NOVA_VOICE_DEBUG=true to print wake verification details
enable_voice_debug = get_env("NOVA_VOICE_DEBUG", "false").lower() == "true"
ENABLE_VOICE_DEBUG = enable_voice_debug

# STT Configs
NEBIUS_STT_URL = os.environ.get("NEBIUS_STT_URL", "https://api.studio.nebius.ai/v1/audio/transcriptions")
NEBIUS_MODEL_NAME = os.environ.get("NEBIUS_MODEL_NAME", "whisper-1")
API_TIMEOUT = 10.0         # HTTP Request timeout in seconds
RETRY_COUNT = 3            # Max STT HTTP retries

# TTS Configs
VOICE_NAME = get_env("NOVA_TTS_VOICE", "en-US-GuyNeural")

# Speaker Verification Configs
# Set NOVA_SPEAKER_VERIFY=false to disable entirely.
enable_speaker_verification = get_env("NOVA_SPEAKER_VERIFY", "true").lower() == "true"
speaker_similarity_threshold = float(get_env("NOVA_SPEAKER_THRESHOLD", "0.75"))
FUSION_TRIGGER_THRESHOLD = float(get_env("NOVA_FUSION_TRIGGER_THRESHOLD", "0.50"))
# Fusion engine component weights — must sum to ~1.0
FUSION_WEIGHT_WAKE    = float(get_env("NOVA_FUSION_WEIGHT_WAKE",    "0.40"))
FUSION_WEIGHT_SPEAKER = float(get_env("NOVA_FUSION_WEIGHT_SPEAKER", "0.30"))
FUSION_WEIGHT_VAD     = float(get_env("NOVA_FUSION_WEIGHT_VAD",     "0.15"))
FUSION_WEIGHT_QUALITY = float(get_env("NOVA_FUSION_WEIGHT_QUALITY", "0.10"))
FUSION_WEIGHT_NOISE   = float(get_env("NOVA_FUSION_WEIGHT_NOISE",   "0.05"))
_OLD_SPEAKER_PATH = os.path.expanduser("~/.config/nova/speaker_embedding.bin")
_NEW_SPEAKER_PATH = os.path.expanduser("~/.config/nova/speaker_embedding.bin")
_default_speaker_path = _OLD_SPEAKER_PATH if os.path.exists(_OLD_SPEAKER_PATH) else _NEW_SPEAKER_PATH
speaker_embedding_path = os.path.expanduser(
    get_env("NOVA_SPEAKER_EMBEDDING", _default_speaker_path)
)
MAX_EMBEDDINGS = int(get_env("NOVA_SPEAKER_MAX_EMBEDDINGS", "50"))

# WebRTC VAD speech padding configs (prevent cutting off start/end of commands)
VAD_PRE_PADDING_FRAMES = 8   # number of 30ms frames (~240ms) to prepend
VAD_POST_PADDING_FRAMES = 12  # number of 30ms frames (~360ms) to append

# Whisper STT Performance Configs
WHISPER_MODEL_SIZE = get_env("NOVA_WHISPER_MODEL", "base")
WHISPER_CPU_THREADS = int(get_env("NOVA_WHISPER_THREADS", "4"))
WHISPER_NUM_WORKERS = int(get_env("NOVA_WHISPER_WORKERS", "1"))
WHISPER_BEAM_SIZE = int(get_env("NOVA_WHISPER_BEAM_SIZE", "5"))

# Diagnostics Configs
_OLD_DIAGNOSTICS_PATH = os.path.expanduser("~/.config/nova/voice_diagnostics.log")
_NEW_DIAGNOSTICS_PATH = os.path.expanduser("~/.config/nova/voice_diagnostics.log")
_default_diagnostics_path = _OLD_DIAGNOSTICS_PATH if os.path.exists(_OLD_DIAGNOSTICS_PATH) else _NEW_DIAGNOSTICS_PATH
DIAGNOSTICS_LOG_PATH = os.path.expanduser(
    get_env("NOVA_DIAGNOSTICS_LOG", _default_diagnostics_path)
)

# Shared runtime variables for voice feedback interruption
active_stream = None
active_wake_detector = None
active_diagnostics = None   # VoiceDiagnosticsEngine instance (set by conversation loop)
interrupt_speaking = False
stream_lock = threading.Lock()

# ChatGPT Response Reading Configs
READ_CHATGPT_RESPONSES = get_env("READ_CHATGPT_RESPONSES", "True").lower() == "true"

