"""Nova v3.0 Phase 1 Automated Test Suite: Nova Mobile Foundation."""

import pytest
import time
from nova.mobile.core import MobileCoreManager
from nova.mobile.plugins import PluginManager, MobilePlugin
from nova.mobile.lifecycle import LifecycleManager
from nova.mobile.scheduler import TaskScheduler, MobileTask
from nova.mobile.storage import MobileDatabase
from nova.mobile.settings import ConfigurationManager, MobileConfig
from nova.mobile.security import MobileSecurityManager
from nova.mobile.communication import CommunicationBridge, MobileCommand, ExecutionTarget


def test_plugin_manager_lifecycle():
    pm = PluginManager()
    pm.initialize()
    assert pm.get_active_count() == 0

    p1 = MobilePlugin("p1", "Plugin One")
    p2 = MobilePlugin("p2", "Plugin Two", dependencies=["p1"])

    assert pm.register_plugin(p1) is True
    assert p1.is_enabled is True
    assert pm.get_active_count() == 1

    assert pm.register_plugin(p2) is True
    assert pm.get_active_count() == 2

    assert pm.unregister_plugin("p2") is True
    assert pm.get_active_count() == 1

    pm.shutdown_all()
    assert pm.get_active_count() == 0


def test_lifecycle_manager_event_pubsub():
    lm = LifecycleManager()
    lm.initialize()

    received_events = []
    listener = lambda evt: received_events.append(evt)
    lm.subscribe(listener)

    lm.publish_event("AppStarted", {"version": "3.0.0"})
    lm.publish_event("BatteryLow", {"level": 10})

    assert len(received_events) == 2
    assert received_events[0].event_name == "AppStarted"
    assert received_events[1].event_name == "BatteryLow"
    assert len(lm.get_event_history()) == 2


def test_task_scheduler_execution_and_cancellation():
    scheduler = TaskScheduler()
    scheduler.initialize()
    assert scheduler.is_running is True

    executed = []
    task1 = MobileTask("t1", "Test Task 1", action=lambda: executed.append(1) or True)

    tid = scheduler.schedule_immediate(task1)
    assert len(executed) == 1
    assert tid == "t1"

    scheduler.cancel_all()
    assert scheduler.is_running is False


def test_mobile_database_crud():
    db = MobileDatabase()
    db.initialize()
    assert db.is_open is True

    db.save_setting("theme", "dark")
    assert db.get_setting("theme") == "dark"

    cmd = db.record_command("device.info", "success")
    assert cmd.action == "device.info"
    assert len(db.get_recent_commands()) == 1

    evt = db.record_event("BatteryLow", '{"level":12}')
    assert evt.type == "BatteryLow"
    assert len(db.get_recent_events()) == 1

    db.close()
    assert db.is_open is False


def test_configuration_manager_updates():
    cm = ConfigurationManager()
    cm.initialize()
    assert cm.config.version == "3.0.0"

    cm.update_config(MobileConfig(environment="production", debug_logging=True))
    assert cm.config.debug_logging is True


def test_mobile_security_manager():
    sm = MobileSecurityManager()
    sm.initialize()
    assert sm.is_ready is True

    token = sm.generate_session_token()
    assert sm.validate_session_token(token) is True

    sm.revoke_session_token(token)
    assert sm.validate_session_token(token) is False


def test_communication_bridge_target_routing():
    cb = CommunicationBridge()
    cb.initialize()

    cmd_local = MobileCommand(action="local.test", preferred_target=ExecutionTarget.LOCAL)
    res = cb.execute_command(cmd_local)
    assert res.executed_by == ExecutionTarget.LOCAL
    assert res.status == "success"

    cb.shutdown()


def test_mobile_core_manager_full_lifecycle():
    core = MobileCoreManager.get_instance()
    assert core.initialize() is True
    assert core.is_initialized is True

    health = core.get_health_status()
    assert health["version"] == "3.0.0"
    assert health["is_initialized"] is True

    core.shutdown()
    assert core.is_initialized is False
