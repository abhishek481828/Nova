import numpy as np
from nova.voice.config import VAD_THRESHOLD

class VoiceActivityDetector:
    """
    Local Voice Activity Detection (VAD) to identify active speech chunks offline
    without using cloud STT resources.
    """
    def __init__(self, threshold: float = VAD_THRESHOLD):
        self.threshold = threshold

    def is_voice_active(self, audio_chunk: np.ndarray) -> bool:
        """
        Detects voice activity in an audio chunk based on Root Mean Square (RMS) energy.
        """
        if audio_chunk is None or len(audio_chunk) == 0:
            return False
        # Compute RMS
        rms = np.sqrt(np.mean(np.square(audio_chunk)))
        return float(rms) >= self.threshold
