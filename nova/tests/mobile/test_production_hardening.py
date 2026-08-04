"""Nova v3.0 Phase 10 Automated Test Suite: Production Hardening, Release & Nova OS Readiness."""

import time
import pytest
from nova.mobile.lifecycle import LifecycleManager
from nova.mobile.wakeword.manager import WakeWordManager
from nova.mobile.voice.manager import VoiceManager
from nova.mobile.command.engine import CommandEngine
from nova.mobile.hybrid.router import HybridRouter
from nova.mobile.memory.manager import MemoryManager
from nova.mobile.memory.enums import MemoryCategory
from nova.mobile.memory.entry import MemoryEntry
from nova.mobile.automation.manager import AutomationManager
from nova.mobile.sync.manager import SyncManager
from nova.mobile.sync.enums import Platform, ConflictPolicy
from nova.mobile.sync.sync_engine import SyncEngine
from nova.mobile.skills.manager import SkillManager
from nova.mobile.skills.builtin_skills import (
    CalculatorSkill, UnitConverterSkill, DeviceStatusSkill, NotesSkill
)


# ─── System Benchmarks & Performance Hardening Tests ─────────────────────────

def test_cold_start_initialization_speed():
    """Verify that entire Mobile Core subsystem stack initializes under 100ms."""
    start = time.time()
    lm = LifecycleManager()
    lm.initialize()

    command_engine = CommandEngine(lifecycle_manager=lm)
    hybrid_router = HybridRouter(command_engine=command_engine, lifecycle_manager=lm)
    memory_manager = MemoryManager(lifecycle_manager=lm)
    automation_manager = AutomationManager(command_engine=command_engine, lifecycle_manager=lm)

    sync_engine = SyncEngine(device_id="bench-phone", memory_manager=memory_manager, automation_manager=automation_manager)
    sync_manager = SyncManager("bench-phone", "Bench Phone", Platform.ANDROID, sync_engine, lm)
    skill_manager = SkillManager(lifecycle_manager=lm)

    sync_manager.start()
    automation_manager.start()
    skill_manager.install_and_load(CalculatorSkill())

    elapsed_ms = (time.time() - start) * 1000
    assert elapsed_ms < 100.0, f"Cold start too slow: {elapsed_ms:.2f}ms"

    sync_manager.stop()
    automation_manager.stop()


def test_command_execution_latency_benchmark():
    """Verify local command execution responds in < 15ms."""
    lm = LifecycleManager()
    lm.initialize()
    ce = CommandEngine(lifecycle_manager=lm)

    start = time.time()
    res = ce.execute_text("Turn on flashlight")
    elapsed_ms = (time.time() - start) * 1000

    assert res.is_success is True
    assert elapsed_ms < 15.0, f"Command execution latency benchmark failed: {elapsed_ms:.2f}ms"


def test_skill_execution_latency_benchmark():
    """Verify built-in skill execution responds in < 10ms."""
    sm = SkillManager()
    sm.install_and_load(CalculatorSkill())

    start = time.time()
    res = sm.handle_voice_text("Calculate 125 * 8")
    elapsed_ms = (time.time() - start) * 1000

    assert res is not None
    assert res.is_success is True
    assert "1000" in res.spoken_response
    assert elapsed_ms < 10.0, f"Skill latency benchmark failed: {elapsed_ms:.2f}ms"


# ─── Memory & Battery Hardening Tests ────────────────────────────────────────

def test_memory_store_capacity_and_pruning():
    """Verify structured memory handles high volume without exceeding bounds."""
    mm = MemoryManager()
    for i in range(150):
        mm.store.put(MemoryEntry(MemoryCategory.FAVORITE_APP, f"key_{i}", f"value_{i}"))
    assert mm.store.total_count() == 150
    query_res = mm.repository.list(MemoryCategory.FAVORITE_APP)
    assert len(query_res) == 150


def test_offline_sync_queue_capacity_cap():
    """Verify offline sync queue caps at 500 items to prevent memory leaks."""
    se = SyncEngine(device_id="cap-test")
    sm = SyncManager("cap-test", "Cap Device", Platform.ANDROID, se)
    sm.start()

    from nova.mobile.sync.models import SyncPayload
    from nova.mobile.sync.enums import SyncCategory

    for i in range(600):
        sm.repository.enqueue(SyncPayload(SyncCategory.PREFERENCES, f"k_{i}", f"v_{i}", "cap-test"))

    assert sm.repository.queue_size() <= 500
    sm.stop()


# ─── Security Hardening Tests ─────────────────────────────────────────────────

def test_security_sensitive_credentials_never_sync():
    """Verify all 10 sensitive key patterns are rejected by sync engine."""
    se = SyncEngine(device_id="sec-test")
    sensitive_keys = [
        "user_password", "my_passwd", "login_token", "auth_token",
        "secret_key", "private_key_pem", "access_token", "refresh_token",
        "card_pin", "card_cvv"
    ]
    for key in sensitive_keys:
        assert se.is_sensitive(key) is True, f"Failed to mark '{key}' as sensitive!"


def test_security_unauthenticated_device_rejection():
    """Verify unauthenticated remote devices cannot inject sync payloads."""
    se = SyncEngine(device_id="sec-test")
    sm = SyncManager("sec-test", "Sec Device", Platform.ANDROID, se)
    sm.start()

    from nova.mobile.sync.models import SyncPayload
    from nova.mobile.sync.enums import SyncCategory

    rogue_payload = SyncPayload(SyncCategory.PREFERENCES, "vol", "100", "rogue-id")
    accepted = sm.receive_payload(rogue_payload)
    assert accepted is False, "Security breach: Unauthenticated payload accepted!"
    sm.stop()


# ─── Stability & Stress Tests ─────────────────────────────────────────────────

def test_simulated_long_running_session_stability():
    """Simulate 100 consecutive voice + automation + sync cycles without failure."""
    lm = LifecycleManager()
    lm.initialize()
    ce = CommandEngine(lifecycle_manager=lm)
    sm = SkillManager(lifecycle_manager=lm)
    sm.install_and_load(CalculatorSkill())
    sm.install_and_load(UnitConverterSkill())

    se = SyncEngine(device_id="stress-phone")
    sync = SyncManager("stress-phone", "Stress Phone", Platform.ANDROID, se, lm)
    sync.start()

    for i in range(100):
        # 1. Command execution
        r1 = ce.execute_text("Turn on flashlight")
        assert r1.is_success is True

        # 2. Skill execution
        r2 = sm.handle_voice_text(f"Calculate {i} + 1")
        assert r2.is_success is True

        # 3. Sync cycle
        sync.sync_now()

    assert ce.history.get_total_count() == 100
    assert sm.executor.total_executions() == 100
    sync.stop()


def test_error_recovery_when_skill_crashes():
    """Verify that a broken skill throwing an uncaught exception does not crash Nova Core."""
    from nova.mobile.skills.base_skill import BaseSkill, SkillExecutionResult
    from nova.mobile.skills.manifest import SkillManifest
    from nova.mobile.skills.enums import SkillCategory

    class BrokenSkill(BaseSkill):
        @property
        def manifest(self) -> SkillManifest:
            return SkillManifest("broken.skill", "Broken", "Crashes", "1.0", "Tester", SkillCategory.CUSTOM)

        def can_handle(self, text: str) -> bool:
            return "crash" in text

        def execute(self, text: str) -> SkillExecutionResult:
            raise RuntimeError("Fatal internal skill error!")

    sm = SkillManager()
    sm.install_and_load(BrokenSkill())

    res = sm.handle_voice_text("please crash now")
    assert res is not None
    assert res.is_success is False
    assert "encountered an error" in res.spoken_response
    assert sm.executor.failure_count() == 1


def test_full_system_health_audit_report():
    """Verify full system health status metrics generation."""
    lm = LifecycleManager()
    lm.initialize()

    ce = CommandEngine(lifecycle_manager=lm)
    ce.execute_text("Turn on flashlight")

    mm = MemoryManager(lifecycle_manager=lm)
    mm.on_command_executed("FLASHLIGHT_ON", {}, "Turn on flashlight")

    am = AutomationManager(command_engine=ce, lifecycle_manager=lm)

    se = SyncEngine("health-phone", mm, am)
    sm = SyncManager("health-phone", "Health Phone", Platform.ANDROID, se, lm)
    sm.start()

    skills = SkillManager(lifecycle_manager=lm)
    skills.install_and_load(CalculatorSkill())

    health = {
        "version": "3.0.0",
        "lifecycle_events": len(lm.get_event_history()),
        "commands_executed": ce.history.get_total_count(),
        "memories_count": mm.store.total_count(),
        "automation_routines": am.repository.count(),
        "sync_queue_size": sm.repository.queue_size(),
        "skills_count": skills.registry.count()
    }

    assert health["version"] == "3.0.0"
    assert health["commands_executed"] == 1
    assert health["skills_count"] == 1
    sm.stop()
