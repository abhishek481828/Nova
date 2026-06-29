import importlib.util

def check_voice_dependencies() -> list[tuple[str, str]]:
    """
    Checks if all optional voice dependencies are installed.
    Uses importlib.util.find_spec to check package availability
    WITHOUT importing/loading them, preventing library dynamic linking
    failures in Text Mode.
    Returns a list of tuples: (dependency_name, reason).
    """
    issues = []
    dependencies = [
        ("numpy", "numpy"),
        ("sounddevice", "sounddevice"),
        ("edge-tts", "edge_tts"),
        ("scipy", "scipy"),
        ("python-dotenv", "dotenv"),
        ("requests", "requests"),
        ("httpx", "httpx"),
        ("soundfile", "soundfile")
    ]
    
    for label, module_name in dependencies:
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                issues.append((label, f"No module named '{module_name}'"))
        except Exception as e:
            issues.append((label, str(e)))
            
    return issues
