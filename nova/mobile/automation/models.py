"""Automation Data Models — Routine, Trigger, Condition, Action, Result."""

import uuid
import time
from typing import List, Dict, Optional, Set
from nova.mobile.automation.enums import (
    TriggerType, ConditionType, ActionType, AutomationStatus
)


class AutomationTrigger:
    def __init__(
        self,
        trigger_type: TriggerType,
        voice_phrase: Optional[str] = None,
        time_hour: Optional[int] = None,
        time_minute: Optional[int] = None,
        days_of_week: Optional[Set[int]] = None,
        battery_threshold: Optional[int] = None,
        bluetooth_device: Optional[str] = None,
        wifi_ssid: Optional[str] = None,
        app_package: Optional[str] = None
    ):
        self.type = trigger_type
        self.voice_phrase = voice_phrase
        self.time_hour = time_hour
        self.time_minute = time_minute
        self.days_of_week = days_of_week or set()
        self.battery_threshold = battery_threshold
        self.bluetooth_device = bluetooth_device
        self.wifi_ssid = wifi_ssid
        self.app_package = app_package


class AutomationCondition:
    def __init__(
        self,
        condition_type: ConditionType,
        int_value: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ):
        self.type = condition_type
        self.int_value = int_value
        self.start_time = start_time
        self.end_time = end_time


class AutomationAction:
    def __init__(
        self,
        action_type: ActionType,
        params: Optional[Dict[str, str]] = None,
        delay_seconds_after: int = 0
    ):
        self.type = action_type
        self.params = params or {}
        self.delay_seconds_after = delay_seconds_after


class Routine:
    def __init__(
        self,
        name: str,
        trigger: AutomationTrigger,
        actions: List[AutomationAction],
        description: str = "",
        conditions: Optional[List[AutomationCondition]] = None,
        status: AutomationStatus = AutomationStatus.ENABLED,
        requires_confirmation: bool = False,
        routine_id: Optional[str] = None
    ):
        self.id = routine_id or str(uuid.uuid4())
        self.name = name
        self.description = description
        self.trigger = trigger
        self.conditions = conditions or []
        self.actions = actions
        self.status = status
        self.requires_confirmation = requires_confirmation
        self.created_at = time.time()
        self.updated_at = time.time()
        self.last_executed_at: Optional[float] = None
        self.execution_count: int = 0


class AutomationResult:
    def __init__(
        self,
        routine_id: str,
        routine_name: str,
        is_success: bool,
        executed_actions: Optional[List[str]] = None,
        failed_action: Optional[str] = None,
        error_message: Optional[str] = None,
        execution_time_ms: int = 0
    ):
        self.routine_id = routine_id
        self.routine_name = routine_name
        self.is_success = is_success
        self.executed_actions = executed_actions or []
        self.failed_action = failed_action
        self.error_message = error_message
        self.execution_time_ms = execution_time_ms
        self.triggered_at = time.time()
