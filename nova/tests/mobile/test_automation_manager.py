"""Nova v3.0 Phase 7 Automated Test Suite: Smart Automation & Routine Engine."""

import pytest
from nova.mobile.automation.enums import (
    TriggerType, ConditionType, ActionType, AutomationStatus
)
from nova.mobile.automation.models import (
    AutomationTrigger, AutomationCondition, AutomationAction, Routine, AutomationResult
)
from nova.mobile.automation.condition_engine import ConditionEngine
from nova.mobile.automation.action_executor import ActionExecutor, ActionLog
from nova.mobile.automation.repository import AutomationRepository
from nova.mobile.automation.manager import (
    AutomationHistory, TriggerManager, RoutineManager,
    AutomationScheduler, AutomationManager
)
from nova.mobile.lifecycle import LifecycleManager


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_routine(name="Morning", trigger_type=TriggerType.MANUAL,
                 voice_phrase=None, actions=None, time_h=None, time_m=None,
                 conditions=None, status=AutomationStatus.ENABLED) -> Routine:
    trigger = AutomationTrigger(
        trigger_type=trigger_type,
        voice_phrase=voice_phrase,
        time_hour=time_h,
        time_minute=time_m
    )
    if actions is None:
        actions = [AutomationAction(ActionType.FLASHLIGHT_ON)]
    return Routine(name=name, trigger=trigger, actions=actions,
                   conditions=conditions or [], status=status)


# ─── AutomationRepository Tests ───────────────────────────────────────────────

def test_repository_save_and_get():
    repo = AutomationRepository()
    r = make_routine("Morning")
    assert repo.save(r) is True
    assert repo.get(r.id) is not None
    assert repo.get(r.id).name == "Morning"


def test_repository_delete():
    repo = AutomationRepository()
    r = make_routine("Night")
    repo.save(r)
    assert repo.delete(r.id) is True
    assert repo.get(r.id) is None


def test_repository_get_enabled_only():
    repo = AutomationRepository()
    repo.save(make_routine("A", status=AutomationStatus.ENABLED))
    repo.save(make_routine("B", status=AutomationStatus.DISABLED))
    enabled = repo.get_enabled()
    assert len(enabled) == 1
    assert enabled[0].name == "A"


def test_repository_set_status():
    repo = AutomationRepository()
    r = make_routine("Drive")
    repo.save(r)
    repo.set_status(r.id, AutomationStatus.DISABLED)
    assert repo.get(r.id).status == AutomationStatus.DISABLED


def test_repository_duplicate():
    repo = AutomationRepository()
    r = make_routine("Sleep")
    repo.save(r)
    copy = repo.duplicate(r.id)
    assert copy is not None
    assert copy.name == "Sleep (Copy)"
    assert copy.id != r.id
    assert copy.status == AutomationStatus.DISABLED


def test_repository_export_and_import():
    repo = AutomationRepository()
    repo.save(make_routine("Work"))
    exported = repo.export()
    assert len(exported) == 1
    assert exported[0]["name"] == "Work"

    # Import into fresh repo
    new_repo = AutomationRepository()
    routines_to_import = [make_routine("Imported")]
    count = new_repo.import_routines(routines_to_import)
    assert count == 1


def test_repository_record_execution():
    repo = AutomationRepository()
    r = make_routine("Gym")
    repo.save(r)
    repo.record_execution(r.id)
    assert repo.get(r.id).execution_count == 1


# ─── ConditionEngine Tests ────────────────────────────────────────────────────

def test_condition_engine_empty_passes():
    ce = ConditionEngine()
    assert ce.evaluate([]) is True


def test_condition_battery_above():
    ce = ConditionEngine()
    ce.battery_level = 80
    c = AutomationCondition(ConditionType.BATTERY_ABOVE, int_value=50)
    assert ce.evaluate([c]) is True


def test_condition_battery_below_fail():
    ce = ConditionEngine()
    ce.battery_level = 80
    c = AutomationCondition(ConditionType.BATTERY_BELOW, int_value=50)
    assert ce.evaluate([c]) is False


def test_condition_wifi_connected():
    ce = ConditionEngine()
    ce.is_wifi_connected = True
    c = AutomationCondition(ConditionType.WIFI_CONNECTED)
    assert ce.evaluate([c]) is True


def test_condition_charging():
    ce = ConditionEngine()
    ce.is_charging = False
    c = AutomationCondition(ConditionType.CHARGING)
    assert ce.evaluate([c]) is False


def test_condition_screen_locked():
    ce = ConditionEngine()
    ce.is_screen_locked = True
    assert ce.evaluate([AutomationCondition(ConditionType.SCREEN_LOCKED)]) is True
    assert ce.evaluate([AutomationCondition(ConditionType.SCREEN_UNLOCKED)]) is False


def test_condition_nova_core_online():
    ce = ConditionEngine()
    ce.is_nova_core_online = True
    assert ce.evaluate([AutomationCondition(ConditionType.NOVA_CORE_ONLINE)]) is True


def test_condition_multiple_all_must_pass():
    ce = ConditionEngine()
    ce.battery_level = 90
    ce.is_wifi_connected = False
    conditions = [
        AutomationCondition(ConditionType.BATTERY_ABOVE, int_value=50),
        AutomationCondition(ConditionType.WIFI_CONNECTED)
    ]
    assert ce.evaluate(conditions) is False


# ─── ActionExecutor Tests ─────────────────────────────────────────────────────

def test_action_executor_no_engine():
    executor = ActionExecutor(command_engine=None)
    actions = [AutomationAction(ActionType.FLASHLIGHT_ON)]
    logs = executor.execute(actions)
    assert len(logs) == 1
    assert logs[0].is_success is True


def test_action_executor_multiple_actions():
    executor = ActionExecutor(command_engine=None)
    actions = [
        AutomationAction(ActionType.FLASHLIGHT_ON),
        AutomationAction(ActionType.SET_BRIGHTNESS, params={"value": "60"})
    ]
    logs = executor.execute(actions)
    assert len(logs) == 2


# ─── TriggerManager Tests ─────────────────────────────────────────────────────

def test_trigger_manager_manual():
    repo = AutomationRepository()
    r = make_routine("Morning", trigger_type=TriggerType.MANUAL)
    repo.save(r)
    tm = TriggerManager(repo)
    fired = []
    tm.add_listener(lambda routine: fired.append(routine.name))
    result = tm.trigger_manual(r.id)
    assert result is True
    assert "Morning" in fired


def test_trigger_manager_manual_disabled_does_not_fire():
    repo = AutomationRepository()
    r = make_routine("Sleep", trigger_type=TriggerType.MANUAL, status=AutomationStatus.DISABLED)
    repo.save(r)
    tm = TriggerManager(repo)
    fired = []
    tm.add_listener(lambda routine: fired.append(routine.name))
    result = tm.trigger_manual(r.id)
    assert result is False
    assert len(fired) == 0


def test_trigger_manager_voice_command():
    repo = AutomationRepository()
    r = make_routine("Drive", trigger_type=TriggerType.VOICE_COMMAND, voice_phrase="driving mode")
    repo.save(r)
    tm = TriggerManager(repo)
    fired = []
    tm.add_listener(lambda routine: fired.append(routine.name))
    tm.on_voice_command("Enable driving mode")
    assert "Drive" in fired


def test_trigger_manager_time_tick():
    repo = AutomationRepository()
    r = make_routine("Morning", trigger_type=TriggerType.TIME, time_h=7, time_m=0)
    repo.save(r)
    tm = TriggerManager(repo)
    fired = []
    tm.add_listener(lambda routine: fired.append(routine.name))
    tm.on_time_tick(7, 0)
    assert "Morning" in fired


def test_trigger_manager_wrong_time_does_not_fire():
    repo = AutomationRepository()
    r = make_routine("Morning", trigger_type=TriggerType.TIME, time_h=7, time_m=0)
    repo.save(r)
    tm = TriggerManager(repo)
    fired = []
    tm.add_listener(lambda routine: fired.append(routine.name))
    tm.on_time_tick(8, 30)
    assert len(fired) == 0


def test_trigger_manager_bluetooth():
    repo = AutomationRepository()
    trigger = AutomationTrigger(TriggerType.BLUETOOTH_CONNECTED, bluetooth_device="CarBT")
    r = Routine("Drive", trigger, [AutomationAction(ActionType.OPEN_APP, {"app": "Maps"})])
    repo.save(r)
    tm = TriggerManager(repo)
    fired = []
    tm.add_listener(lambda routine: fired.append(routine.name))
    tm.on_bluetooth_connected("CarBT")
    assert "Drive" in fired


# ─── RoutineManager Tests ─────────────────────────────────────────────────────

def test_routine_manager_voice_list():
    repo = AutomationRepository()
    tm = TriggerManager(repo)
    rm = RoutineManager(repo, tm)
    repo.save(make_routine("Morning"))
    repo.save(make_routine("Night"))
    resp = rm.handle_voice_query("What routines do I have?")
    assert resp is not None
    assert "Morning" in resp
    assert "Night" in resp


def test_routine_manager_voice_enable():
    repo = AutomationRepository()
    r = make_routine("Office", status=AutomationStatus.DISABLED)
    repo.save(r)
    tm = TriggerManager(repo)
    rm = RoutineManager(repo, tm)
    resp = rm.handle_voice_query("Enable my office routine")
    assert resp is not None
    assert "enabled" in resp.lower()
    assert repo.get(r.id).status == AutomationStatus.ENABLED


def test_routine_manager_voice_disable():
    repo = AutomationRepository()
    r = make_routine("Sleep")
    repo.save(r)
    tm = TriggerManager(repo)
    rm = RoutineManager(repo, tm)
    resp = rm.handle_voice_query("Disable sleep routine")
    assert resp is not None
    assert "disabled" in resp.lower()


def test_routine_manager_pause_all():
    repo = AutomationRepository()
    repo.save(make_routine("A"))
    repo.save(make_routine("B"))
    tm = TriggerManager(repo)
    rm = RoutineManager(repo, tm)
    resp = rm.handle_voice_query("Pause all automations")
    assert resp is not None
    assert rm.all_paused is True


def test_routine_manager_resume_all():
    repo = AutomationRepository()
    repo.save(make_routine("A"))
    tm = TriggerManager(repo)
    rm = RoutineManager(repo, tm)
    rm.pause_all()
    resp = rm.handle_voice_query("Resume all automations")
    assert resp is not None
    assert rm.all_paused is False


# ─── AutomationManager Integration Tests ──────────────────────────────────────

def test_automation_manager_executes_manual_routine():
    lm = LifecycleManager()
    lm.initialize()
    mgr = AutomationManager(lifecycle_manager=lm)
    r = make_routine("Flash", trigger_type=TriggerType.MANUAL)
    mgr.repository.save(r)
    mgr.start()
    mgr.trigger_manager.trigger_manual(r.id)
    last = mgr.history.get_last_result()
    assert last is not None
    assert last.routine_name == "Flash"
    assert last.is_success is True
    mgr.stop()


def test_automation_manager_condition_blocks_execution():
    mgr = AutomationManager()
    mgr.condition_engine.is_wifi_connected = False
    conditions = [AutomationCondition(ConditionType.WIFI_CONNECTED)]
    r = make_routine("WiFi-Only", conditions=conditions)
    mgr.repository.save(r)
    mgr.start()
    mgr.trigger_manager.trigger_manual(r.id)
    assert mgr.history.total_count() == 0   # condition blocked it
    mgr.stop()


def test_automation_manager_pause_prevents_execution():
    mgr = AutomationManager()
    r = make_routine("Blocked")
    mgr.repository.save(r)
    mgr.start()
    mgr.routine_manager.pause_all()
    mgr.trigger_manager.trigger_manual(r.id)
    assert mgr.history.total_count() == 0
    mgr.stop()


def test_automation_manager_scheduler_time_tick():
    lm = LifecycleManager()
    lm.initialize()
    mgr = AutomationManager(lifecycle_manager=lm)
    r = make_routine("7AM", trigger_type=TriggerType.TIME, time_h=7, time_m=0)
    mgr.repository.save(r)
    mgr.start()
    mgr.scheduler.simulate_tick(7, 0)
    last = mgr.history.get_last_result()
    assert last is not None
    assert last.routine_name == "7AM"
    mgr.stop()


def test_automation_events_published():
    lm = LifecycleManager()
    lm.initialize()
    mgr = AutomationManager(lifecycle_manager=lm)
    r = make_routine("Events")
    mgr.repository.save(r)
    mgr.start()
    mgr.trigger_manager.trigger_manual(r.id)
    events = [e.event_name for e in lm.get_event_history()]
    assert "AutomationManagerStarted" in events
    assert "RoutineExecutionStarted" in events
    assert "RoutineExecutionSucceeded" in events
    mgr.stop()


# ─── History Tests ────────────────────────────────────────────────────────────

def test_history_records_and_filters():
    h = AutomationHistory()
    h.record(AutomationResult("id1", "Morning", True, execution_time_ms=100))
    h.record(AutomationResult("id2", "Night", False, error_message="timeout"))
    assert h.total_count() == 2
    assert h.success_count() == 1
    assert h.failure_count() == 1
    failed = h.get_failed()
    assert len(failed) == 1
    assert failed[0].routine_name == "Night"


def test_history_get_for_routine():
    h = AutomationHistory()
    h.record(AutomationResult("r1", "Morning", True))
    h.record(AutomationResult("r1", "Morning", True))
    h.record(AutomationResult("r2", "Night", False))
    assert len(h.get_for_routine("r1")) == 2


# ─── Error Handling Tests ─────────────────────────────────────────────────────

def test_delete_nonexistent_routine():
    repo = AutomationRepository()
    assert repo.delete("nonexistent-id") is False


def test_trigger_manual_nonexistent():
    repo = AutomationRepository()
    tm = TriggerManager(repo)
    assert tm.trigger_manual("nonexistent-id") is False


def test_voice_query_no_match():
    repo = AutomationRepository()
    tm = TriggerManager(repo)
    rm = RoutineManager(repo, tm)
    resp = rm.handle_voice_query("Call Pankaj")
    assert resp is None
