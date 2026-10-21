import os
import importlib.util

def check_voice_dependencies() -> list[tuple[str, str]]:
    """
    Checks if all required voice dependencies are installed.
    Cloud-supported features (e.g. Deepgram STT, Edge TTS) satisfy requirements
    without needing heavy local models.
    Returns a list of tuples: (dependency_name, reason) for any missing required components.
    """
    issues = []
    required_dependencies = [
        ("numpy", "numpy"),
        ("sounddevice", "sounddevice"),
        ("scipy", "scipy"),
        ("soundfile", "soundfile"),
        ("httpx", "httpx"),
        ("edge_tts", "edge_tts"),
    ]
    
    for label, module_name in required_dependencies:
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                issues.append((label, f"No module named '{module_name}'"))
        except Exception as e:
            issues.append((label, str(e)))

    # STT Check: If Deepgram API key is present, local faster_whisper is not required
    has_deepgram = bool(os.environ.get("DEEPGRAM_API_KEY"))
    if not has_deepgram:
        try:
            if importlib.util.find_spec("faster_whisper") is None:
                issues.append(("faster_whisper", "No local faster_whisper model and no DEEPGRAM_API_KEY configured."))
        except Exception as e:
            issues.append(("faster_whisper", str(e)))
            
    return issues


def get_diagnostics():
    """
    Return the active VoiceDiagnosticsEngine instance registered by the
    voice conversation loop, or None if the voice loop is not running.
    """
    try:
        import nova.voice.config as _cfg
        return _cfg.active_diagnostics
    except Exception:
        return None
