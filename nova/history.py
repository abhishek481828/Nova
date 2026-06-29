import json
from datetime import datetime
from typing import Any, Dict, List
from nova.config import HISTORY_JSON_PATH
from nova.logger import log_error

# Ensure config directory exists
HISTORY_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

class HistoryManager:
    @staticmethod
    def load_history() -> List[Dict[str, Any]]:
        """Load interaction history from history.json."""
        if not HISTORY_JSON_PATH.exists():
            return []
        try:
            with open(HISTORY_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            log_error("Failed to load history file", e)
            return []

    @staticmethod
    def save_history(history: List[Dict[str, Any]]) -> None:
        """Save interaction history to history.json."""
        try:
            with open(HISTORY_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
        except Exception as e:
            log_error("Failed to save history file", e)

    @classmethod
    def add_entry(
        cls,
        user_input: str,
        parsed_action: Dict[str, Any],
        executed_commands: List[str],
        status: str,
        result_message: str = "",
    ) -> None:
        """Add a new history entry."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "parsed_action": parsed_action,
            "executed_commands": executed_commands,
            "status": status,
            "result_message": result_message,
        }
        history = cls.load_history()
        history.append(entry)
        cls.save_history(history)

    @classmethod
    def print_history(cls, limit: int = 10) -> None:
        """Print recent history entries."""
        from nova.utils import COLOR_BOLD, COLOR_RESET, COLOR_RED, _write
        entries = cls.load_history()
        if not entries:
            _write("No history entries found.\n")
            return

        header = f"{COLOR_BOLD}=== Recent Nova History (last {min(limit, len(entries))} entries) ==={COLOR_RESET}\n"
        _write(header)
        for entry in entries[-limit:]:
            timestamp = entry.get("timestamp", "")
            try:
                ts_formatted = timestamp.split(".")[0].replace("T", " ")
            except Exception:
                ts_formatted = timestamp
            user_input = entry.get("user_input", "")
            status = entry.get("status", "")
            executed_commands = entry.get("executed_commands", [])

            status_color = COLOR_RESET
            if status == "success":
                status_color = "\033[92m"  # Light green
            elif "failed" in status or "error" in status or "exception" in status:
                status_color = COLOR_RED

            _write(f"[{ts_formatted}] {COLOR_BOLD}Input:{COLOR_RESET} {user_input}\n")
            _write(f"  {COLOR_BOLD}Status:{COLOR_RESET} {status_color}{status}{COLOR_RESET}\n")
            if executed_commands:
                _write(f"  {COLOR_BOLD}Commands:{COLOR_RESET} {', '.join(executed_commands)}\n")
            _write("\n")
