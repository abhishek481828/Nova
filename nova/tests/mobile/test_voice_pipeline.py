"""Nova v3.0 Phase 3 Automated Test Suite: Voice Pipeline & Speech Recognition."""

import pytest
from nova.mobile.core import MobileCoreManager
from nova.mobile.lifecycle import LifecycleManager
from nova.mobile.voice.config import VoiceConfiguration
from nova.mobile.voice.session import VoiceSession, VoiceState
from nova.mobile.voice.speech_recognizer import SpeechRecognizerManager
from nova.mobile.voice.metrics import VoiceMetrics
from nova.mobile.voice.manager import VoiceManager
import nova.mobile.voice.events as evt_consts


def test_voice_configuration_defaults():
    cfg = VoiceConfiguration()
    assert cfg.language == "en-US"
    assert cfg.silence_timeout_ms == 3000
    assert cfg.max_recording_duration_ms == 10000
    assert cfg.wake_sound_enabled is True
    assert cfg.partial_results_enabled is True


def test_voice_session_state_machine():
    session = VoiceSession()
    assert session.current_state == VoiceState.IDLE

    session.transition_to(VoiceState.LISTENING)
    assert session.current_state == VoiceState.LISTENING

    session.transition_to(VoiceState.RECORDING)
    assert session.current_state == VoiceState.RECORDING

    session.transition_to(VoiceState.COMPLETED)
    assert session.current_state == VoiceState.COMPLETED
    assert session.get_duration_ms() >= 0


def test_speech_recognizer_manager_lifecycle():
    srm = SpeechRecognizerManager()
    assert srm.is_listening is False

    assert srm.initialize() is True
    srm.start_listening("en-US", True)
    assert srm.is_listening is True

    srm.stop_listening()
    assert srm.is_listening is False


def test_voice_manager_speech_recognition_pipeline():
    lm = LifecycleManager()
    lm.initialize()

    vm = VoiceManager(lifecycle_manager=lm)
    session = vm.start_voice_session()
    assert session.current_state == VoiceState.RECORDING

    recognized_texts = []
    vm.result_listeners.append(lambda text, confidence: recognized_texts.append((text, confidence)))

    vm.simulate_recognized_text("Call Pankaj", confidence=0.98)

    assert len(recognized_texts) == 1
    assert recognized_texts[0][0] == "Call Pankaj"
    assert recognized_texts[0][1] == 0.98

    history = lm.get_event_history()
    event_names = [e.event_name for e in history]
    assert evt_consts.EVENT_LISTENING_STARTED in event_names
    assert evt_consts.EVENT_SPEECH_RECOGNIZED in event_names

    assert vm.metrics.total_sessions == 1
    assert vm.metrics.last_recognized_text == "Call Pankaj"


def test_voice_manager_session_cancellation():
    lm = LifecycleManager()
    lm.initialize()

    vm = VoiceManager(lifecycle_manager=lm)
    session = vm.start_voice_session()
    assert session.current_state == VoiceState.RECORDING

    vm.cancel_voice_session()
    assert session.current_state == VoiceState.CANCELLED

    history = lm.get_event_history()
    event_names = [e.event_name for e in history]
    assert evt_consts.EVENT_RECOGNITION_CANCELLED in event_names


def test_automatic_wake_word_to_voice_pipeline_trigger():
    core = MobileCoreManager.get_instance()
    core.initialize()

    # Trigger wake word detection
    core.wake_word_manager.trigger_wake_detection(score=0.96)

    # Verify voice session started automatically
    assert core.voice_manager.current_session is not None
    assert core.voice_manager.current_session.current_state == VoiceState.RECORDING

    # Simulate recognized text
    core.voice_manager.simulate_recognized_text("Call Pankaj on WhatsApp", confidence=0.99)
    assert core.voice_manager.metrics.last_recognized_text == "Call Pankaj on WhatsApp"

    health = core.get_health_status()
    assert health["last_recognized_text"] == "Call Pankaj on WhatsApp"

    core.shutdown()
