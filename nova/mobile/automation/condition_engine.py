"""ConditionEngine — Evaluates pre-conditions before running a routine."""

import logging
from datetime import datetime, time as dt_time
from typing import List
from nova.mobile.automation.models import AutomationCondition
from nova.mobile.automation.enums import ConditionType

logger = logging.getLogger("nova.mobile.automation.condition_engine")


class ConditionEngine:
    def __init__(self):
        self.battery_level: int = 100
        self.is_charging: bool = False
        self.is_headphones_connected: bool = False
        self.is_wifi_connected: bool = False
        self.is_screen_locked: bool = False
        self.is_nova_core_online: bool = False

    def evaluate(self, conditions: List[AutomationCondition]) -> bool:
        for condition in conditions:
            if not self._evaluate_single(condition):
                logger.info(f"Condition NOT met: {condition.type} → routine blocked")
                return False
        return True

    def _evaluate_single(self, condition: AutomationCondition) -> bool:
        t = condition.type
        if t == ConditionType.BATTERY_ABOVE:
            return self.battery_level > (condition.int_value or 20)
        if t == ConditionType.BATTERY_BELOW:
            return self.battery_level < (condition.int_value or 20)
        if t == ConditionType.WIFI_CONNECTED:
            return self.is_wifi_connected
        if t == ConditionType.CHARGING:
            return self.is_charging
        if t == ConditionType.HEADPHONES_CONNECTED:
            return self.is_headphones_connected
        if t == ConditionType.SCREEN_LOCKED:
            return self.is_screen_locked
        if t == ConditionType.SCREEN_UNLOCKED:
            return not self.is_screen_locked
        if t == ConditionType.NOVA_CORE_ONLINE:
            return self.is_nova_core_online
        if t == ConditionType.TIME_RANGE:
            return self._is_within_time_range(condition.start_time, condition.end_time)
        return True

    def _is_within_time_range(self, start: str, end: str) -> bool:
        if not start or not end:
            return True
        try:
            now = datetime.now().time()
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
            s = dt_time(sh, sm)
            e = dt_time(eh, em)
            return s <= now <= e
        except Exception:
            logger.warning(f"Invalid time range: {start}–{end}")
            return False
