"""AutomationHistory, TriggerManager, RoutineManager, AutomationScheduler, AutomationManager."""

import time
import logging
from collections import deque
from typing import List, Optional, Callable, Dict
from nova.mobile.automation.models import Routine, AutomationResult
from nova.mobile.automation.enums import TriggerType, AutomationStatus

logger = logging.getLogger("nova.mobile.automation")


# ─── AutomationHistory ────────────────────────────────────────────────────────

class AutomationHistory:
    def __init__(self, max_size: int = 100):
        self._history: deque = deque(maxlen=max_size)

    def record(self, result: AutomationResult):
        self._history.append(result)
        status = "SUCCESS" if result.is_success else "FAILED"
        logger.info(f"[{status}] Routine '{result.routine_name}' in {result.execution_time_ms}ms")

    def get_all(self) -> List[AutomationResult]:
        return list(reversed(self._history))

    def get_recent(self, limit: int = 10) -> List[AutomationResult]:
        return self.get_all()[:limit]

    def get_failed(self) -> List[AutomationResult]:
        return [r for r in self.get_all() if not r.is_success]

    def get_for_routine(self, routine_id: str) -> List[AutomationResult]:
        return [r for r in self.get_all() if r.routine_id == routine_id]

    def get_last_result(self) -> Optional[AutomationResult]:
        return self._history[-1] if self._history else None

    def total_count(self) -> int:
        return len(self._history)

    def success_count(self) -> int:
        return sum(1 for r in self._history if r.is_success)

    def failure_count(self) -> int:
        return sum(1 for r in self._history if not r.is_success)

    def clear(self):
        self._history.clear()


# ─── TriggerManager ───────────────────────────────────────────────────────────

class TriggerManager:
    def __init__(self, repository):
        self._repository = repository
        self._listeners: List[Callable[[Routine], None]] = []

    def on_voice_command(self, spoken_text: str):
        text = spoken_text.lower().strip()
        for r in self._repository.get_enabled():
            if (r.trigger.type == TriggerType.VOICE_COMMAND and
                    r.trigger.voice_phrase and r.trigger.voice_phrase.lower() in text):
                self._fire(r, f"VOICE:{spoken_text}")

    def on_screen_on(self):    self._fire_by_type(TriggerType.SCREEN_ON, "SCREEN_ON")
    def on_screen_off(self):   self._fire_by_type(TriggerType.SCREEN_OFF, "SCREEN_OFF")
    def on_battery_charging(self): self._fire_by_type(TriggerType.BATTERY_CHARGING, "CHARGING")
    def on_headphones_connected(self): self._fire_by_type(TriggerType.HEADPHONES_CONNECTED, "HEADPHONES")
    def on_nova_core_connected(self): self._fire_by_type(TriggerType.NOVA_CORE_CONNECTED, "CORE_CONNECTED")
    def on_nova_core_disconnected(self): self._fire_by_type(TriggerType.NOVA_CORE_DISCONNECTED, "CORE_DISCONNECTED")

    def on_bluetooth_connected(self, device: str):
        for r in self._repository.get_enabled():
            if r.trigger.type == TriggerType.BLUETOOTH_CONNECTED and \
               (not r.trigger.bluetooth_device or r.trigger.bluetooth_device == device):
                self._fire(r, f"BT:{device}")

    def on_wifi_connected(self, ssid: str):
        for r in self._repository.get_enabled():
            if r.trigger.type == TriggerType.WIFI_CONNECTED and \
               (not r.trigger.wifi_ssid or r.trigger.wifi_ssid == ssid):
                self._fire(r, f"WIFI:{ssid}")

    def on_time_tick(self, hour: int, minute: int):
        for r in self._repository.get_enabled():
            if r.trigger.type == TriggerType.TIME and \
               r.trigger.time_hour == hour and r.trigger.time_minute == minute:
                self._fire(r, f"TIME:{hour:02d}:{minute:02d}")

    def trigger_manual(self, routine_id: str) -> bool:
        r = self._repository.get(routine_id)
        if not r or r.status != AutomationStatus.ENABLED:
            return False
        self._fire(r, "MANUAL")
        return True

    def add_listener(self, listener: Callable[[Routine], None]):
        self._listeners.append(listener)

    def _fire_by_type(self, trigger_type: TriggerType, source: str):
        for r in self._repository.get_enabled():
            if r.trigger.type == trigger_type:
                self._fire(r, source)

    def _fire(self, routine: Routine, source: str):
        logger.info(f"Trigger fired: '{routine.name}' from {source}")
        for listener in self._listeners:
            try:
                listener(routine)
            except Exception:
                logger.error("Error in trigger listener", exc_info=True)


# ─── AutomationScheduler ──────────────────────────────────────────────────────

class AutomationScheduler:
    def __init__(self, trigger_manager: TriggerManager):
        self._trigger_manager = trigger_manager
        self.is_running = False

    def simulate_tick(self, hour: int, minute: int):
        """Used in tests to manually fire a time tick."""
        self._trigger_manager.on_time_tick(hour, minute)

    def start(self):
        self.is_running = True
        logger.info("AutomationScheduler started")

    def stop(self):
        self.is_running = False
        logger.info("AutomationScheduler stopped")


# ─── RoutineManager ───────────────────────────────────────────────────────────

LIST_TRIGGERS = ["what routines", "list routines", "show routines", "my routines"]
PAUSE_ALL_TRIGGERS = ["pause all", "pause automations", "stop all routines"]
RESUME_ALL_TRIGGERS = ["resume all", "enable all routines", "resume automations"]


class RoutineManager:
    def __init__(self, repository, trigger_manager: TriggerManager):
        self._repository = repository
        self._trigger_manager = trigger_manager
        self.all_paused: bool = False

    def create_routine(self, routine: Routine) -> bool:
        return self._repository.save(routine)

    def update_routine(self, routine: Routine) -> bool:
        return self._repository.save(routine)

    def delete_routine(self, routine_id: str) -> bool:
        return self._repository.delete(routine_id)

    def enable_routine(self, routine_id: str) -> bool:
        return self._repository.set_status(routine_id, AutomationStatus.ENABLED)

    def disable_routine(self, routine_id: str) -> bool:
        return self._repository.set_status(routine_id, AutomationStatus.DISABLED)

    def duplicate_routine(self, routine_id: str) -> Optional[Routine]:
        return self._repository.duplicate(routine_id)

    def pause_all(self):
        self.all_paused = True
        for r in self._repository.get_enabled():
            self._repository.set_status(r.id, AutomationStatus.PAUSED)
        logger.info("All automations paused")

    def resume_all(self):
        self.all_paused = False
        for r in self._repository.get_all():
            if r.status == AutomationStatus.PAUSED:
                self._repository.set_status(r.id, AutomationStatus.ENABLED)
        logger.info("All automations resumed")

    def handle_voice_query(self, raw_text: str) -> Optional[str]:
        clean = raw_text.lower().strip()

        if any(t in clean for t in LIST_TRIGGERS):
            return self._build_list_response()
        if any(t in clean for t in PAUSE_ALL_TRIGGERS):
            self.pause_all()
            return "All automations have been paused."
        if any(t in clean for t in RESUME_ALL_TRIGGERS):
            self.resume_all()
            return "All automations have been resumed."

        for routine in self._repository.get_all():
            name_lower = routine.name.lower()
            if ("enable" in clean or "activate" in clean) and name_lower in clean:
                self.enable_routine(routine.id)
                return f"Done. '{routine.name}' is now enabled."
            if ("disable" in clean or "turn off" in clean) and name_lower in clean:
                self.disable_routine(routine.id)
                return f"Done. '{routine.name}' is now disabled."
            if ("delete" in clean or "remove" in clean) and name_lower in clean:
                self.delete_routine(routine.id)
                return f"Done. I've deleted your '{routine.name}' routine."
            if ("run" in clean or "execute" in clean or "start" in clean) and name_lower in clean:
                self._trigger_manager.trigger_manual(routine.id)
                return f"Running '{routine.name}' now."
        return None

    def _build_list_response(self) -> str:
        routines = self._repository.get_all()
        if not routines:
            return "You don't have any routines yet."
        lines = [f"You have {len(routines)} routine(s):"]
        for r in routines:
            status = {"ENABLED": "🟢 enabled", "DISABLED": "⚪ disabled",
                      "PAUSED": "⏸ paused"}.get(r.status.value, r.status.value.lower())
            lines.append(f"• {r.name} — {status} ({len(r.actions)} actions, ran {r.execution_count}×)")
        return "\n".join(lines)


# ─── AutomationManager ────────────────────────────────────────────────────────

class AutomationManager:
    def __init__(self, command_engine=None, lifecycle_manager=None):
        from nova.mobile.automation.repository import AutomationRepository
        from nova.mobile.automation.condition_engine import ConditionEngine
        from nova.mobile.automation.action_executor import ActionExecutor

        self.repository = AutomationRepository()
        self.history = AutomationHistory()
        self.condition_engine = ConditionEngine()
        self.action_executor = ActionExecutor(command_engine)
        self.trigger_manager = TriggerManager(self.repository)
        self.routine_manager = RoutineManager(self.repository, self.trigger_manager)
        self.scheduler = AutomationScheduler(self.trigger_manager)
        self._lifecycle_manager = lifecycle_manager
        self._result_listeners: List[Callable[[AutomationResult], None]] = []

        self.trigger_manager.add_listener(self._execute_routine)

    def start(self):
        self.scheduler.start()
        self._publish("AutomationManagerStarted", {})
        logger.info("AutomationManager started")

    def stop(self):
        self.scheduler.stop()
        self._publish("AutomationManagerStopped", {})

    def _execute_routine(self, routine: Routine):
        if self.routine_manager.all_paused:
            logger.warning(f"Automations paused — skipping '{routine.name}'")
            return

        start_time = time.time()
        self._publish("RoutineExecutionStarted", {"routineId": routine.id, "name": routine.name})

        if not self.condition_engine.evaluate(routine.conditions):
            logger.info(f"Conditions not met for '{routine.name}' — skipping")
            self._publish("RoutineConditionFailed", {"routineId": routine.id})
            return

        action_logs = []
        try:
            action_logs = self.action_executor.execute(routine.actions)
        except Exception as e:
            logger.error(f"Routine '{routine.name}' crashed: {e}", exc_info=True)

        elapsed_ms = int((time.time() - start_time) * 1000)
        failed = next((a for a in action_logs if not a.is_success), None)
        is_success = failed is None

        result = AutomationResult(
            routine_id=routine.id,
            routine_name=routine.name,
            is_success=is_success,
            executed_actions=[a.action_type for a in action_logs if a.is_success],
            failed_action=failed.action_type if failed else None,
            error_message=failed.error_message if failed else None,
            execution_time_ms=elapsed_ms
        )
        self.history.record(result)
        self.repository.record_execution(routine.id)

        event = "RoutineExecutionSucceeded" if is_success else "RoutineExecutionFailed"
        self._publish(event, {"routineId": routine.id, "name": routine.name,
                              "elapsed": elapsed_ms})
        for listener in self._result_listeners:
            try:
                listener(result)
            except Exception:
                logger.error("Error in result listener", exc_info=True)

    def handle_voice_query(self, raw_text: str) -> Optional[str]:
        return self.routine_manager.handle_voice_query(raw_text)

    def add_result_listener(self, listener: Callable[[AutomationResult], None]):
        self._result_listeners.append(listener)

    def _publish(self, event_name: str, payload: dict):
        if self._lifecycle_manager:
            self._lifecycle_manager.publish_event(event_name, payload)
