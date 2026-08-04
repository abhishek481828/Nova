"""Execution Result Data Model."""

from typing import Optional
from nova.mobile.hybrid.strategy import ExecutionTarget


class ExecutionResult:
    def __init__(
        self,
        request_id: str,
        intent: str,
        target: ExecutionTarget,
        is_success: bool,
        spoken_response: str,
        execution_time_ms: int = 0,
        network_latency_ms: int = 0,
        error_message: Optional[str] = None,
        used_fallback: bool = False
    ):
        self.request_id = request_id
        self.intent = intent
        self.target = target
        self.is_success = is_success
        self.spoken_response = spoken_response
        self.execution_time_ms = execution_time_ms
        self.network_latency_ms = network_latency_ms
        self.error_message = error_message
        self.used_fallback = used_fallback
