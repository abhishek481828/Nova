"""Nova v3.0 Phase 5 Automated Test Suite: Hybrid AI Router & Intelligent Task Orchestration."""

import pytest
from nova.mobile.core import MobileCoreManager
from nova.mobile.lifecycle import LifecycleManager
from nova.mobile.command.engine import CommandEngine
from nova.mobile.hybrid.strategy import ExecutionTarget, RoutingPolicy
from nova.mobile.hybrid.capability_resolver import CapabilityResolver
from nova.mobile.hybrid.device_discovery import DeviceDiscovery
from nova.mobile.hybrid.routing_engine import RoutingEngine
from nova.mobile.hybrid.execution_planner import ExecutionPlanner
from nova.mobile.hybrid.router import HybridRouter


# ─── Capability Resolver Tests ───────────────────────────────────────────────

def test_capability_resolver_phone_intents():
    cr = CapabilityResolver()
    assert cr.resolve_target("CALL_CONTACT", "Call Pankaj") == ExecutionTarget.LOCAL_ANDROID
    assert cr.resolve_target("FLASHLIGHT_ON", "Turn on flashlight") == ExecutionTarget.LOCAL_ANDROID
    assert cr.resolve_target("SET_BRIGHTNESS", "Set brightness to 70") == ExecutionTarget.LOCAL_ANDROID
    assert cr.resolve_target("OPEN_APP", "Open YouTube") == ExecutionTarget.LOCAL_ANDROID


def test_capability_resolver_nova_core_keywords():
    cr = CapabilityResolver()
    assert cr.resolve_target("UNKNOWN", "Explain binary search") == ExecutionTarget.NOVA_CORE
    assert cr.resolve_target("UNKNOWN", "Summarize my project") == ExecutionTarget.NOVA_CORE
    assert cr.resolve_target("UNKNOWN", "What is quantum computing") == ExecutionTarget.NOVA_CORE
    assert cr.resolve_target("UNKNOWN", "Write code for sorting") == ExecutionTarget.NOVA_CORE


# ─── Routing Engine Tests ─────────────────────────────────────────────────────

def test_routing_engine_automatic_local_when_core_offline():
    cr = CapabilityResolver()
    dd = DeviceDiscovery()
    dd.simulate_online(False)  # Nova Core offline
    engine = RoutingEngine(cr, dd, policy=RoutingPolicy.AUTOMATIC)

    # Phone intent → always local
    assert engine.decide("CALL_CONTACT", "Call Pankaj") == ExecutionTarget.LOCAL_ANDROID
    # Core-required text → degraded local (core offline)
    assert engine.decide("UNKNOWN", "Explain quantum computing") == ExecutionTarget.LOCAL_ANDROID


def test_routing_engine_automatic_core_when_online():
    cr = CapabilityResolver()
    dd = DeviceDiscovery()
    dd.simulate_online(True, latency_ms=15)  # Nova Core online
    engine = RoutingEngine(cr, dd, policy=RoutingPolicy.AUTOMATIC)

    assert engine.decide("UNKNOWN", "Explain quantum computing") == ExecutionTarget.NOVA_CORE
    assert engine.decide("CALL_CONTACT", "Call Pankaj") == ExecutionTarget.LOCAL_ANDROID


def test_routing_policy_always_local():
    cr = CapabilityResolver()
    dd = DeviceDiscovery()
    dd.simulate_online(True)
    engine = RoutingEngine(cr, dd, policy=RoutingPolicy.ALWAYS_LOCAL)

    # Even Core-required text → forced local
    assert engine.decide("UNKNOWN", "Explain dynamic programming") == ExecutionTarget.LOCAL_ANDROID


def test_routing_policy_offline_mode():
    cr = CapabilityResolver()
    dd = DeviceDiscovery()
    dd.simulate_online(True)
    engine = RoutingEngine(cr, dd, policy=RoutingPolicy.OFFLINE_MODE)

    assert engine.decide("UNKNOWN", "Summarize my project") == ExecutionTarget.LOCAL_ANDROID


# ─── Hybrid Router Tests ──────────────────────────────────────────────────────

def test_hybrid_router_local_execution():
    lm = LifecycleManager()
    lm.initialize()
    ce = CommandEngine(lifecycle_manager=lm)
    router = HybridRouter(command_engine=ce, lifecycle_manager=lm)
    router.device_discovery.simulate_online(False)

    result = router.route("Call Pankaj", "CALL_CONTACT")
    assert result.target == ExecutionTarget.LOCAL_ANDROID
    assert result.is_success is True
    assert "Calling Pankaj" in result.spoken_response


def test_hybrid_router_nova_core_forwarding_when_online():
    lm = LifecycleManager()
    lm.initialize()
    ce = CommandEngine(lifecycle_manager=lm)
    router = HybridRouter(command_engine=ce, lifecycle_manager=lm)
    router.device_discovery.simulate_online(True, latency_ms=12)

    result = router.route("Explain binary search", "UNKNOWN")
    assert result.target == ExecutionTarget.NOVA_CORE
    assert result.is_success is True
    assert "Nova Core" in result.spoken_response or "Forwarded" in result.spoken_response


def test_hybrid_router_offline_graceful_degradation():
    lm = LifecycleManager()
    lm.initialize()
    ce = CommandEngine(lifecycle_manager=lm)
    router = HybridRouter(command_engine=ce, lifecycle_manager=lm)
    router.device_discovery.simulate_online(False)  # Core offline

    result = router.route("Explain quantum computing", "UNKNOWN")
    assert result.is_success is False
    assert "Nova Core" in result.spoken_response
    assert "unavailable" in result.spoken_response


def test_hybrid_router_events_published():
    lm = LifecycleManager()
    lm.initialize()
    ce = CommandEngine(lifecycle_manager=lm)
    router = HybridRouter(command_engine=ce, lifecycle_manager=lm)
    router.device_discovery.simulate_online(False)

    router.route("Turn on flashlight", "FLASHLIGHT_ON")
    event_names = [e.event_name for e in lm.get_event_history()]
    assert "HybridRouted" in event_names
    assert "HybridLocalExecuted" in event_names


# ─── Full Pipeline Integration Test ───────────────────────────────────────────

def test_full_pipeline_wake_to_hybrid_router_local():
    core = MobileCoreManager.get_instance()
    core.initialize()
    core.hybrid_router.device_discovery.simulate_online(False)

    # 1. Wake word detected
    core.wake_word_manager.trigger_wake_detection(score=0.97)

    # 2. User says "Call Pankaj" → should execute locally
    core.voice_manager.simulate_recognized_text("Call Pankaj", confidence=0.99)

    last = core.hybrid_router.get_last_result()
    assert last is not None
    assert last.target == ExecutionTarget.LOCAL_ANDROID
    assert "Calling Pankaj" in last.spoken_response

    health = core.get_health_status()
    assert health["nova_core_online"] is False
    assert health["routing_policy"] == "AUTOMATIC"

    core.shutdown()


def test_full_pipeline_wake_to_hybrid_router_nova_core():
    core = MobileCoreManager.get_instance()
    core.initialize()
    core.hybrid_router.device_discovery.simulate_online(True, latency_ms=8)

    # 1. Wake word detected
    core.wake_word_manager.trigger_wake_detection(score=0.97)

    # 2. User says "Explain binary search" → should forward to Nova Core
    core.voice_manager.simulate_recognized_text("Explain binary search", confidence=0.99)

    last = core.hybrid_router.get_last_result()
    assert last is not None
    assert last.target == ExecutionTarget.NOVA_CORE

    core.shutdown()
