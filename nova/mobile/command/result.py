"""Command Execution Result Data Model."""

from typing import Dict, Optional
from nova.mobile.command.registry import BuiltInIntent


class CommandResult:
    def __init__(
        self,
        command_id: str,
        intent: BuiltInIntent,
        is_success: bool,
        spoken_response: str,
        plugin_used: str,
        entities: Dict[str, str] = None,
        execution_time_ms: int = 0,
        error_message: Optional[str] = None
    ):
        self.command_id = command_id
        self.intent = intent
        self.is_success = is_success
        self.spoken_response = spoken_response
        self.plugin_used = plugin_used
        self.entities = entities or {}
        self.execution_time_ms = execution_time_ms
        self.error_message = error_message
