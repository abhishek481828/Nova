"""Voice Pipeline Manager Python Binding."""

import logging
from typing import List, Callable
from nova.mobile.voice.config import VoiceConfiguration
from nova.mobile.voice.session import VoiceSession, VoiceState
from nova.mobile.voice.speech_recognizer import SpeechRecognizerManager
from nova.mobile.voice.metrics import VoiceMetrics
import nova.mobile.voice.events as evt_consts

logger = logging.getLogger("nova.mobile.voice.manager")


class VoiceManager:
    def __init__(self, lifecycle_manager=None, config: VoiceConfiguration = None):
        self.lifecycle_manager = lifecycle_manager
        self.config = config or VoiceConfiguration()
        self.speech_recognizer_manager = SpeechRecognizerManager()
        self.metrics = VoiceMetrics()
        self.current_session: VoiceSession = None
        self.result_listeners: List[Callable[[str, float], None]] = []

    def start_voice_session(self) -> VoiceSession:
        if self.current_session and self.current_session.current_state in (VoiceState.LISTENING, VoiceState.RECORDING):
            self.cancel_voice_session()

        session = VoiceSession()
        self.current_session = session
        session.transition_to(VoiceState.LISTENING)

        if self.lifecycle_manager:
            self.lifecycle_manager.publish_event(evt_consts.EVENT_LISTENING_STARTED, {"sessionId": session.session_id})

        self.speech_recognizer_manager.start_listening(self.config.language, self.config.partial_results_enabled)
        session.transition_to(VoiceState.RECORDING)
        return session

    def stop_voice_session(self):
        if not self.current_session:
            return
        self.current_session.transition_to(VoiceState.RECOGNIZING)
        self.speech_recognizer_manager.stop_listening()
        if self.lifecycle_manager:
            self.lifecycle_manager.publish_event(evt_consts.EVENT_LISTENING_STOPPED, {"sessionId": self.current_session.session_id})

    def cancel_voice_session(self):
        if not self.current_session:
            return
        self.speech_recognizer_manager.stop_listening()
        self.current_session.transition_to(VoiceState.CANCELLED)
        if self.lifecycle_manager:
            self.lifecycle_manager.publish_event(evt_consts.EVENT_RECOGNITION_CANCELLED, {"sessionId": self.current_session.session_id})

    def simulate_recognized_text(self, text: str, confidence: float = 0.95):
        session = self.current_session or self.start_voice_session()
        duration_ms = session.get_duration_ms()

        self.metrics.record_recognition(text, confidence, duration_ms, self.config.language)
        session.transition_to(VoiceState.COMPLETED)

        if self.lifecycle_manager:
            self.lifecycle_manager.publish_event(evt_consts.EVENT_SPEECH_ENDED, {"sessionId": session.session_id})
            self.lifecycle_manager.publish_event(
                evt_consts.EVENT_SPEECH_RECOGNIZED,
                {
                    "text": text,
                    "confidence": confidence,
                    "duration_ms": duration_ms,
                    "language": self.config.language
                }
            )

        for l in self.result_listeners:
            l(text, confidence)
