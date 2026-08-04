"""Wake Word Engine Python Binding."""

import logging
from nova.mobile.wakeword.config import WakeWordConfiguration

logger = logging.getLogger("nova.mobile.wakeword.engine")


class WakeWordEngine:
    def __init__(self, config: WakeWordConfiguration = None):
        self.config = config or WakeWordConfiguration()
        self.is_active = False

    def start(self) -> bool:
        self.is_active = True
        return True

    def process_audio_frame(self, data: bytes) -> float:
        if not self.is_active or not data:
            return 0.0
        return 0.95 if len(data) > 0 else 0.0

    def stop(self):
        self.is_active = False
