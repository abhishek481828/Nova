"""Voice Pipeline Performance Metrics."""

class VoiceMetrics:
    def __init__(self):
        self.total_sessions = 0
        self.successful_recognitions = 0
        self.last_recognized_text = ""
        self.last_confidence = 0.0
        self.last_session_duration_ms = 0
        self.last_recognition_language = "en-US"

    def record_recognition(self, text: str, confidence: float = 0.95, duration_ms: int = 1200, lang: str = "en-US"):
        self.total_sessions += 1
        self.successful_recognitions += 1
        self.last_recognized_text = text
        self.last_confidence = confidence
        self.last_session_duration_ms = duration_ms
        self.last_recognition_language = lang
