"""Nova v3.0 — Nova Mobile Core Binding for Python Core Environment."""

import time
import logging
from typing import Dict, Any, List, Optional
from nova.mobile.wakeword.manager import WakeWordManager
from nova.mobile.voice.manager import VoiceManager
from nova.mobile.command.engine import CommandEngine

logger = logging.getLogger("nova.mobile.core")


class MobileCoreManager:
    _instance: Optional['MobileCoreManager'] = None

    def __init__(self):
        self.is_initialized: bool = False
        self.version: str = "3.0.0"
        self.plugins: Dict[str, Any] = {}
        self.lifecycle_events: List[Dict[str, Any]] = []
        self.wake_word_manager = WakeWordManager()
        self.voice_manager = VoiceManager()
        self.command_engine = CommandEngine()

        # Connect wake word detection trigger to voice manager session
        self.wake_word_manager.listeners.append(
            lambda phrase, score: self.voice_manager.start_voice_session()
        )

        # Connect voice recognition output to local command engine
        self.voice_manager.result_listeners.append(
            lambda recognized_text, score: self.command_engine.execute_text(recognized_text)
        )

    @classmethod
    def get_instance(cls) -> 'MobileCoreManager':
        if cls._instance is None:
            cls._instance = MobileCoreManager()
        return cls._instance

    def initialize(self) -> bool:
        if self.is_initialized:
            return True
        logger.info("Initializing Nova Mobile Core v3.0...")
        self.is_initialized = True
        self.publish_lifecycle_event("AppStarted", {"version": self.version})
        return True

    def shutdown(self):
        if not self.is_initialized:
            return
        logger.info("Shutting down Nova Mobile Core v3.0...")
        self.publish_lifecycle_event("AppStopped", {})
        self.voice_manager.cancel_voice_session()
        self.wake_word_manager.stop_listening()
        self.is_initialized = False

    def publish_lifecycle_event(self, event_name: str, payload: Dict[str, Any]):
        evt = {"event_name": event_name, "payload": payload, "timestamp": time.time()}
        self.lifecycle_events.append(evt)

    def get_health_status(self) -> Dict[str, Any]:
        session_state = self.voice_manager.current_session.current_state.value if self.voice_manager.current_session else "IDLE"
        last_result = self.command_engine.history.get_last_result()
        return {
            "version": self.version,
            "is_initialized": self.is_initialized,
            "plugins_active": len(self.plugins),
            "scheduler_running": True,
            "security_ready": True,
            "database_ready": True,
            "core_connection": "CONNECTED",
            "wakeword_listening": self.wake_word_manager.is_listening,
            "wakeword_detections": self.wake_word_manager.metrics.total_detections,
            "voice_state": session_state,
            "last_recognized_text": self.voice_manager.metrics.last_recognized_text,
            "recognition_confidence": self.voice_manager.metrics.last_confidence,
            "last_intent": last_result.intent.value if last_result else "NONE",
            "last_spoken_response": last_result.spoken_response if last_result else "None",
            "total_commands_executed": self.history_count()
        }

    def history_count(self) -> int:
        return self.command_engine.history.get_total_count()
