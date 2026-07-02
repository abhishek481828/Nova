import os
from pathlib import Path

def get_version() -> str:
    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    if version_path.exists():
        try:
            with open(version_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return "1.0.0"

__version__ = get_version()
