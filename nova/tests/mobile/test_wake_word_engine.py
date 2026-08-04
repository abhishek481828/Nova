"""Nova v3.0 Phase 2 Automated Test Suite: Offline Wake Word Engine."""

import pytest
from nova.mobile.core import MobileCoreManager
from nova.mobile.lifecycle import LifecycleManager
from nova.mobile.wakeword.config import WakeWordConfiguration
from nova.mobile.wakeword.mic_manager import MicrophoneManager
from nova.mobile.wakeword.engine import WakeWordEngine
from nova.mobile.wakeword.metrics import WakeWordMetrics
from nova.mobile.wakeword.manager import WakeWordManager
import nova.mobile.wakeword.events as evt_consts


def test_wake_word_configuration_defaults():
    cfg = WakeWordConfiguration()
    assert cfg.wake_phrase == "Hey Nova"
    assert cfg.sensitivity == 0.75
    assert cfg.detection_threshold == 0.80
    assert cfg.wake_sound_enabled is True


def test_microphone_manager_lifecycle():
    mic = MicrophoneManager()
    assert mic.has_record_permission() is True
    assert mic.is_recording is False

    assert mic.start_capturing() is True
    assert mic.is_recording is True

    chunk = mic.read_chunk(512)
    assert len(chunk) == 1024  # 512 samples * 2 bytes/sample (16-bit)

    mic.stop_capturing()
    assert mic.is_recording is False


def test_wake_word_engine_frame_scoring():
    cfg = WakeWordConfiguration(sensitivity=0.85, detection_threshold=0.80)
    engine = WakeWordEngine(cfg)
    assert engine.is_active is False

    assert engine.start() is True
    assert engine.is_active is True

    score_empty = engine.process_audio_frame(b"")
    assert score_empty == 0.0

    score_frame = engine.process_audio_frame(b"\x01\x02" * 256)
    assert score_frame > 0.0

    engine.stop()
    assert engine.is_active is False


def test_wake_word_manager_detection_events():
    lm = LifecycleManager()
    lm.initialize()

    manager = WakeWordManager(lifecycle_manager=lm)
    assert manager.is_listening is False

    assert manager.start_listening() is True
    assert manager.is_listening is True

    detected_callbacks = []
    manager.listeners.append(lambda phrase, confidence: detected_callbacks.append((phrase, confidence)))

    manager.trigger_wake_detection(score=0.96)

    assert len(detected_callbacks) == 1
    assert detected_callbacks[0][0] == "Hey Nova"
    assert detected_callbacks[0][1] == 0.96

    history = lm.get_event_history()
    event_names = [e.event_name for e in history]
    assert evt_consts.EVENT_LISTENING_STARTED in event_names
    assert evt_consts.EVENT_DETECTED in event_names

    manager.stop_listening()
    assert manager.is_listening is False


def test_wake_word_engine_restart_recovery():
    lm = LifecycleManager()
    lm.initialize()

    manager = WakeWordManager(lifecycle_manager=lm)
    manager.start_listening()

    assert manager.restart_engine() is True
    assert manager.metrics.total_recovery_attempts == 1

    history = lm.get_event_history()
    event_names = [e.event_name for e in history]
    assert evt_consts.EVENT_ENGINE_RESTARTED in event_names


def test_mobile_core_integration_with_wake_word():
    core = MobileCoreManager.get_instance()
    core.initialize()

    # Access wakeWordManager from health status
    health = core.get_health_status()
    assert "wakeword_listening" in health
    assert "wakeword_detections" in health

    core.shutdown()
