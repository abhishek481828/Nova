"""Command Execution Log History Python Binding."""

from typing import List, Optional
from nova.mobile.command.result import CommandResult


class CommandHistory:
    def __init__(self):
        self.history: List[CommandResult] = []

    def record(self, result: CommandResult):
        self.history.append(result)

    def get_recent_results(self, limit: int = 10) -> List[CommandResult]:
        return list(reversed(self.history[-limit:]))

    def get_last_result(self) -> Optional[CommandResult]:
        return self.history[-1] if self.history else None

    def get_total_count(self) -> int:
        return len(self.history)
