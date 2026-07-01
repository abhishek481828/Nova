import json
from pathlib import Path
from nova.utils import print_info

STATE_FILE_PATH = Path.home() / ".config" / "nova" / "state.json"

class StateManager:
    _state = {
        "autonomous_mode": False  # Default to False: plans require approval before execution
    }

    @classmethod
    def load_state(cls) -> None:
        """Loads state from the persistent state file."""
        if STATE_FILE_PATH.exists():
            try:
                with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
                    cls._state.update(json.load(f))
            except Exception:
                pass

    @classmethod
    def save_state(cls) -> None:
        """Saves current state to the persistent state file."""
        try:
            STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(cls._state, f, indent=4)
        except Exception:
            pass

    @classmethod
    def is_autonomous(cls) -> bool:
        """Checks if autonomous mode is enabled."""
        return cls._state.get("autonomous_mode", True)

    @classmethod
    def set_autonomous_mode(cls, enabled: bool) -> None:
        """Toggles the autonomous mode state and saves it."""
        cls._state["autonomous_mode"] = enabled
        cls.save_state()
        status = "ENABLED" if enabled else "DISABLED"
        print_info(f"Nova Autonomous Mode is now {status}.")

    @classmethod
    def get_user_profile(cls) -> dict:
        """Returns the persistent user profile dictionary."""
        return cls._state.setdefault("user_profile", {})

    @classmethod
    def update_user_profile(cls, details: dict) -> None:
        """Updates the persistent user profile and saves state."""
        profile = cls.get_user_profile()
        profile.update(details)
        cls.save_state()

# Load state on module import
StateManager.load_state()
