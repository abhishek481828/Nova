"""Nova v3.0 Phase 4 Automated Test Suite: Local Command Engine & Intent System."""

import pytest
from nova.mobile.core import MobileCoreManager
from nova.mobile.lifecycle import LifecycleManager
from nova.mobile.command.registry import BuiltInIntent
from nova.mobile.command.parser import IntentParser
from nova.mobile.command.entity_extractor import EntityExtractor
from nova.mobile.command.context import ExecutionContext
from nova.mobile.command.dispatcher import CommandDispatcher
from nova.mobile.command.engine import CommandEngine


def test_intent_parser_built_in_classification():
    parser = IntentParser()

    assert parser.parse("Call Pankaj") == BuiltInIntent.CALL_CONTACT
    assert parser.parse("Call Mom") == BuiltInIntent.CALL_CONTACT
    assert parser.parse("Open YouTube") == BuiltInIntent.PLAY_YOUTUBE
    assert parser.parse("Open WhatsApp") == BuiltInIntent.OPEN_APP
    assert parser.parse("Play music") == BuiltInIntent.PLAY_YOUTUBE
    assert parser.parse("Set volume to 40 percent") == BuiltInIntent.SET_VOLUME
    assert parser.parse("Set brightness to 80 percent") == BuiltInIntent.SET_BRIGHTNESS
    assert parser.parse("Turn on flashlight") == BuiltInIntent.FLASHLIGHT_ON
    assert parser.parse("Turn off flashlight") == BuiltInIntent.FLASHLIGHT_OFF
    assert parser.parse("Send SMS to Pankaj") == BuiltInIntent.SEND_SMS
    assert parser.parse("Open Chrome") == BuiltInIntent.OPEN_BROWSER
    assert parser.parse("Open Maps") == BuiltInIntent.OPEN_MAPS
    assert parser.parse("Show battery level") == BuiltInIntent.BATTERY_STATUS


def test_entity_extractor_and_pronoun_resolution():
    extractor = EntityExtractor()
    context = ExecutionContext()

    # Step 1: "Call Pankaj"
    entities1 = extractor.extract("Call Pankaj", BuiltInIntent.CALL_CONTACT, context)
    assert entities1["contact"] == "Pankaj"
    assert context.last_contact == "Pankaj"

    # Step 2: "Send him a message" -> Resolves "him" to "Pankaj"
    entities2 = extractor.extract("Send him a message saying Hello", BuiltInIntent.SEND_SMS, context)
    assert entities2["contact"] == "Pankaj"
    assert entities2["message"] == "Hello"


def test_command_dispatcher_spoken_responses():
    dispatcher = CommandDispatcher()

    r1 = dispatcher.dispatch("c1", BuiltInIntent.CALL_CONTACT, {"contact": "Pankaj"})
    assert r1.is_success is True
    assert r1.spoken_response == "Calling Pankaj."
    assert r1.plugin_used == "CallHandler"

    r2 = dispatcher.dispatch("c2", BuiltInIntent.SET_BRIGHTNESS, {"percentage": "70"})
    assert r2.is_success is True
    assert r2.spoken_response == "Brightness set to 70 percent."
    assert r2.plugin_used == "BrightnessHandler"

    r3 = dispatcher.dispatch("c3", BuiltInIntent.FLASHLIGHT_ON, {})
    assert r3.spoken_response == "Flashlight turned on."
    assert r3.plugin_used == "FlashlightHandler"


def test_command_engine_end_to_end_execution():
    lm = LifecycleManager()
    lm.initialize()

    engine = CommandEngine(lifecycle_manager=lm)

    result = engine.execute_text("Call Pankaj")
    assert result.is_success is True
    assert result.intent == BuiltInIntent.CALL_CONTACT
    assert result.spoken_response == "Calling Pankaj."

    history = lm.get_event_history()
    event_names = [e.event_name for e in history]
    assert "IntentRecognized" in event_names
    assert "CommandCompleted" in event_names


def test_full_pipeline_wake_word_to_command_execution():
    core = MobileCoreManager.get_instance()
    core.initialize()

    # 1. User says "Hey Nova" -> Trigger Wake Detection
    core.wake_word_manager.trigger_wake_detection(score=0.97)

    # 2. Voice Pipeline automatically starts -> Simulate user speech: "Open YouTube"
    core.voice_manager.simulate_recognized_text("Open YouTube", confidence=0.99)

    # 3. Verify Local Command Engine parsed intent and executed local plugin
    health = core.get_health_status()
    assert health["last_intent"] in ("PLAY_YOUTUBE", "OPEN_APP")
    assert health["last_spoken_response"] == "Opening YouTube."
    assert health["total_commands_executed"] >= 1

    core.shutdown()
