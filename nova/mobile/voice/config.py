"""Voice Pipeline Configuration."""

class VoiceConfiguration:
    def __init__(
        self,
        language: str = "en-US",
        silence_timeout_ms: int = 3000,
        max_recording_duration_ms: int = 10000,
        min_speech_duration_ms: int = 500,
        wake_sound_enabled: bool = True,
        partial_results_enabled: bool = True,
        microphone_sensitivity: float = 1.0
    ):
        self.language = language
        self.silence_timeout_ms = silence_timeout_ms
        self.max_recording_duration_ms = max_recording_duration_ms
        self.min_speech_duration_ms = min_speech_duration_ms
        self.wake_sound_enabled = wake_sound_enabled
        self.partial_results_enabled = partial_results_enabled
        self.microphone_sensitivity = microphone_sensitivity
