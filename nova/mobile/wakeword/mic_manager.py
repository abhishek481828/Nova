"""Microphone Manager Python Binding."""

import logging

logger = logging.getLogger("nova.mobile.wakeword.mic")


class MicrophoneManager:
    def __init__(self):
        self.has_permission = True
        self.is_recording = False

    def has_record_permission(self) -> bool:
        return self.has_permission

    def start_capturing(self, sample_rate: int = 16000, frame_size: int = 512) -> bool:
        if not self.has_permission:
            return False
        self.is_recording = True
        return True

    def read_chunk(self, size: int = 512) -> bytes:
        if not self.is_recording:
            return b""
        return b"\x00" * (size * 2)

    def stop_capturing(self):
        self.is_recording = False
