import os
import tempfile
try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env", override=True)
except ImportError:
    pass

def get_env(name: str, default: str) -> str:
    # Check NOVA_ prefixed environment variable first, then NOVA_ prefixed one.
    nova_name = name.replace("NOVA_", "NOVA_")
    return os.environ.get(nova_name, os.environ.get(name, default))

ENABLE_VOICE = True
ENABLE_TTS = True

# Preprocessing Pipeline Toggles
ENABLE_NOISE_SUPPRESSION = True   # RNNoise neural denoiser
ENABLE_HIGHPASS_FILTER = True     # Butterworth high-pass (removes fan hum / AC noise)
ENABLE_AGC = True                 # Automatic Gain Control
ENABLE_VAD = True                 # WebRTC Voice Activity Detection
ENABLE_DC_OFFSET_REMOVAL = True   # Subtract mean to remove microphone DC bias
ENABLE_ECHO_CANCEL = False        # Software AEC (requires speex-dsp; disabled by default)

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
CHUNK_DURATION = 0.1       # Duration of each recorded audio chunk in seconds
TEMP_AUDIO_DIR = get_env("NOVA_TEMP_AUDIO_DIR", tempfile.gettempdir())

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

# Resolve built-in model path dynamically inside the virtual environment
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

# Debug Mode — set NOVA_DEBUG=true to enable verbose per-chunk audio logging
enable_debug = get_env("NOVA_DEBUG", "false").lower() == "true"
ENABLE_DEBUG = enable_debug

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
_OLD_SPEAKER_PATH = os.path.expanduser("~/.config/nova/speaker_embedding.bin")
_NEW_SPEAKER_PATH = os.path.expanduser("~/.config/nova/speaker_embedding.bin")
_default_speaker_path = _OLD_SPEAKER_PATH if os.path.exists(_OLD_SPEAKER_PATH) else _NEW_SPEAKER_PATH
speaker_embedding_path = os.path.expanduser(
    get_env("NOVA_SPEAKER_EMBEDDING", _default_speaker_path)
)

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
interrupt_speaking = False
