"""Voice Session State Machine."""

import uuid
import time
from enum import Enum


class VoiceState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    RECORDING = "RECORDING"
    RECOGNIZING = "RECOGNIZING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class VoiceSession:
    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.current_state = VoiceState.IDLE
        self.start_timestamp = time.time()
        self.end_timestamp = 0.0

    def transition_to(self, new_state: VoiceState) -> bool:
        self.current_state = new_state
        if new_state in (VoiceState.COMPLETED, VoiceState.CANCELLED, VoiceState.ERROR):
            self.end_timestamp = time.time()
        return True

    def get_duration_ms(self) -> int:
        end = self.end_timestamp if self.end_timestamp > 0 else time.time()
        return int((end - self.start_timestamp) * 1000)
