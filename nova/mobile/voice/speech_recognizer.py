"""Speech Recognizer Python Binding."""

import logging

logger = logging.getLogger("nova.mobile.voice.speech_recognizer")


class SpeechRecognizerManager:
    def __init__(self):
        self.is_listening = False

    def initialize(self, callback=None) -> bool:
        return True

    def start_listening(self, language: str = "en-US", partial_results: bool = True):
        self.is_listening = True

    def stop_listening(self):
        self.is_listening = False
