"""Wake Word Engine Configuration."""

class WakeWordConfiguration:
    def __init__(
        self,
        wake_phrase: str = "Hey Nova",
        sensitivity: float = 0.75,
        detection_threshold: float = 0.80,
        wake_sound_enabled: bool = True,
        adaptive_sleep_enabled: bool = True,
        audio_sample_rate: int = 16000,
        frame_size_samples: int = 512,
        max_recovery_attempts: int = 5
    ):
        self.wake_phrase = wake_phrase
        self.sensitivity = sensitivity
        self.detection_threshold = detection_threshold
        self.wake_sound_enabled = wake_sound_enabled
        self.adaptive_sleep_enabled = adaptive_sleep_enabled
        self.audio_sample_rate = audio_sample_rate
        self.frame_size_samples = frame_size_samples
        self.max_recovery_attempts = max_recovery_attempts
