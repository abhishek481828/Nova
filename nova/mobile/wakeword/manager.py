"""Wake Word Manager Python Binding."""

import logging
from typing import List, Callable
from nova.mobile.wakeword.config import WakeWordConfiguration
from nova.mobile.wakeword.mic_manager import MicrophoneManager
from nova.mobile.wakeword.engine import WakeWordEngine
from nova.mobile.wakeword.metrics import WakeWordMetrics
import nova.mobile.wakeword.events as evt_consts

logger = logging.getLogger("nova.mobile.wakeword.manager")


class WakeWordManager:
    def __init__(self, lifecycle_manager=None, config: WakeWordConfiguration = None):
        self.lifecycle_manager = lifecycle_manager
        self.config = config or WakeWordConfiguration()
        self.mic_manager = MicrophoneManager()
        self.engine = WakeWordEngine(self.config)
        self.metrics = WakeWordMetrics()
        self.is_listening = False
        self.listeners: List[Callable[[str, float], None]] = []

    def start_listening(self) -> bool:
        if self.is_listening:
            return True

        if not self.mic_manager.has_record_permission():
            if self.lifecycle_manager:
                self.lifecycle_manager.publish_event(evt_consts.EVENT_PERMISSION_MISSING, {})
            return False

        if not self.engine.start():
            if self.lifecycle_manager:
                self.lifecycle_manager.publish_event(evt_consts.EVENT_DETECTION_FAILED, {"reason": "Engine failed"})
            return False

        if not self.mic_manager.start_capturing(self.config.audio_sample_rate, self.config.frame_size_samples):
            self.engine.stop()
            if self.lifecycle_manager:
                self.lifecycle_manager.publish_event(evt_consts.EVENT_DETECTION_FAILED, {"reason": "Mic failed"})
            return False

        self.is_listening = True
        if self.lifecycle_manager:
            self.lifecycle_manager.publish_event(evt_consts.EVENT_LISTENING_STARTED, {"phrase": self.config.wake_phrase})
        return True

    def trigger_wake_detection(self, score: float = 0.95):
        self.metrics.record_detection()
        if self.lifecycle_manager:
            self.lifecycle_manager.publish_event(
                evt_consts.EVENT_DETECTED,
                {
                    "phrase": self.config.wake_phrase,
                    "confidence": score,
                    "count": self.metrics.total_detections
                }
            )
        for l in self.listeners:
            l(self.config.wake_phrase, score)

    fun_stop = lambda self: self.stop_listening()

    def stop_listening(self):
        if not self.is_listening:
            return
        self.mic_manager.stop_capturing()
        self.engine.stop()
        self.is_listening = False
        if self.lifecycle_manager:
            self.lifecycle_manager.publish_event(evt_consts.EVENT_LISTENING_STOPPED, {})

    def restart_engine(self) -> bool:
        self.stop_listening()
        self.metrics.record_recovery()
        success = self.start_listening()
        if success and self.lifecycle_manager:
            self.lifecycle_manager.publish_event(evt_consts.EVENT_ENGINE_RESTARTED, {"attempt": self.metrics.total_recovery_attempts})
        return success
