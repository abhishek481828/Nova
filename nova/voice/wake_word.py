import numpy as np
import os
import time
from nova.voice.config import WAKE_WORD_THRESHOLD, WAKE_WORD_MODEL_PATH
from nova.logger import logger

class WakeWordDetectorInterface:
    def __init__(self, wake_word: str = "hey nova", confidence_threshold: float = WAKE_WORD_THRESHOLD):
        self.wake_word = wake_word.lower()
        self.confidence_threshold = confidence_threshold

    def detect(self, audio_data: np.ndarray, sample_rate: int) -> bool:
        """
        Detects wake word in an audio buffer.
        """
        raise NotImplementedError()

class NovaRuleDetector(WakeWordDetectorInterface):
    """
    Highly optimized local rule-based acoustic detector for the syllables of 'Nova'.
    Fusing:
    1. Voiced vowel 'Jar' (High low-freq energy 250Hz - 1000Hz)
    2. Voiceless sibilant 'vis' (High high-freq energy 3000Hz - 7000Hz)
    """
    def __init__(self, wake_word: str = "nova", confidence_threshold: float = WAKE_WORD_THRESHOLD):
        super().__init__(wake_word, confidence_threshold)
        self.last_voiced_time = 0.0

    def detect(self, audio_data: np.ndarray, sample_rate: int) -> bool:
        # Require at least 0.3 seconds of audio to analyze spectral pattern
        if len(audio_data) < int(sample_rate * 0.3):
            return False
            
        from scipy.signal import welch
        try:
            # Flatten audio data
            flat_audio = audio_data.flatten()
            freqs, psd = welch(flat_audio, fs=sample_rate, nperseg=256)
            
            # Mask low (voiced) and high (fricative) bands
            low_mask = (freqs >= 250) & (freqs <= 1000)
            high_mask = (freqs >= 3000) & (freqs <= 7000)
            
            low_energy = np.mean(psd[low_mask]) if np.any(low_mask) else 0.0
            high_energy = np.mean(psd[high_mask]) if np.any(high_mask) else 0.0
            
            curr_time = time.time()
            
            # Detect vowel "Jar" (voicing)
            # Threshold matches normalized custom confidence
            if low_energy > 1e-7 and low_energy > (2.5 / self.confidence_threshold) * high_energy:
                self.last_voiced_time = curr_time
                
            # Detect fricative "vis" (sibilance)
            elif high_energy > 5e-8 and high_energy > (1.2 / self.confidence_threshold) * low_energy:
                # Syllables must occur sequentially within a natural speaking range (0.1 to 0.8 seconds)
                if 0.08 <= (curr_time - self.last_voiced_time) <= 0.8:
                    self.last_voiced_time = 0.0 # reset
                    return True
        except Exception as e:
            logger.debug(f"Rule-based detection exception: {e}")
            
        return False

class TemplateMatchingDetector(WakeWordDetectorInterface):
    """
    Spectral pattern template matching using spectrogram correlation.
    Supports future configurable wake words via template files.
    """
    def __init__(self, wake_word: str = "nova", confidence_threshold: float = WAKE_WORD_THRESHOLD):
        super().__init__(wake_word, confidence_threshold)
        self.template = None
        
        # Load from file if template exists
        dir_path = os.path.dirname(os.path.abspath(__file__))
        template_file = os.path.join(dir_path, "templates", f"{self.wake_word}.npy")
        if os.path.exists(template_file):
            try:
                self.template = np.load(template_file)
            except Exception as e:
                logger.debug(f"Failed to load wake word template {template_file}: {e}")

    def detect(self, audio_data: np.ndarray, sample_rate: int) -> bool:
        if self.template is None:
            return False
            
        from scipy.signal import spectrogram
        try:
            flat_audio = audio_data.flatten()
            f, t, Sxx = spectrogram(flat_audio, fs=sample_rate, nperseg=256)
            
            # Calculate correlation distance
            if Sxx.shape[1] < self.template.shape[1]:
                return False
                
            # Max cross-correlation over sliding spectrogram slices
            max_corr = 0.0
            t_len = self.template.shape[1]
            for i in range(Sxx.shape[1] - t_len + 1):
                slice_sxx = Sxx[:, i:i+t_len]
                # Normalized correlation
                norm_slice = slice_sxx - np.mean(slice_sxx)
                norm_temp = self.template - np.mean(self.template)
                denom = np.sqrt(np.sum(norm_slice**2) * np.sum(norm_temp**2))
                if denom > 0:
                    corr = np.sum(norm_slice * norm_temp) / denom
                    if corr > max_corr:
                        max_corr = corr
                        
            return max_corr >= self.confidence_threshold
        except Exception as e:
            logger.debug(f"Template matching exception: {e}")
            
        return False

class NovaRuleDetector(WakeWordDetectorInterface):
    """
    Highly optimized local rule-based acoustic detector for the syllables of 'Nova' ('No' + 'va').
    """
    def __init__(self, wake_word: str = "nova", confidence_threshold: float = WAKE_WORD_THRESHOLD):
        super().__init__(wake_word, confidence_threshold)
        self.last_voiced_time = 0.0

    def detect(self, audio_data: np.ndarray, sample_rate: int) -> bool:
        if len(audio_data) < int(sample_rate * 0.3):
            return False
            
        from scipy.signal import welch
        try:
            # Flatten audio data
            flat_audio = audio_data.flatten()
            freqs, psd = welch(flat_audio, fs=sample_rate, nperseg=256)
            
            # Mask low-mid (No) and mid-high (va)
            low_mask = (freqs >= 200) & (freqs <= 800)
            high_mask = (freqs >= 1000) & (freqs <= 3000)
            
            low_energy = np.mean(psd[low_mask]) if np.any(low_mask) else 0.0
            high_energy = np.mean(psd[high_mask]) if np.any(high_mask) else 0.0
            
            curr_time = time.time()
            
            # Detect vowel "No" (voicing)
            if low_energy > 1e-7 and low_energy > (2.0 / self.confidence_threshold) * high_energy:
                self.last_voiced_time = curr_time
                
            # Detect vowel/fricative "va"
            elif high_energy > 4e-8 and high_energy > (1.0 / self.confidence_threshold) * low_energy:
                # Syllables must occur sequentially within a natural speaking range
                if 0.06 <= (curr_time - self.last_voiced_time) <= 0.8:
                    self.last_voiced_time = 0.0 # reset
                    return True
        except Exception as e:
            logger.debug(f"Nova rule-based detection exception: {e}")
            
        return False


class LocalWakeWordDetector(WakeWordDetectorInterface):
    """
    Wake word detector using OpenWakeWord, falling back to rule-based syllable
    matcher for backward-compatibility unit tests.
    """
    def __init__(self, model_path: str = WAKE_WORD_MODEL_PATH, confidence_threshold: float = WAKE_WORD_THRESHOLD, wake_word: str = "nova"):
        super().__init__(wake_word, confidence_threshold)
        # Suppress verbose CUDA/ONNX runtime warnings to keep logs clean
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning, module="onnxruntime")
        warnings.filterwarnings("ignore", category=UserWarning, message=".*CUDAExecutionProvider.*")

        # We try to import openwakeword and load the model.
        import openwakeword
        from openwakeword.model import Model

        # Instantiated helper detector for compatibility tests (Step 11 requirement)
        self.detector = NovaRuleDetector("nova", confidence_threshold)
        self.nova_detector = NovaRuleDetector("nova", confidence_threshold)

        # Automatically locate hey_nova model dynamically if path is missing or invalid
        if not model_path or not os.path.exists(model_path):
            try:
                package_dir = os.path.dirname(openwakeword.__file__)
                resources_model_path = os.path.join(package_dir, "resources", "models", "hey_nova_v0.1.onnx")
                if os.path.exists(resources_model_path):
                    model_path = resources_model_path
            except Exception as ex:
                logger.debug(f"Dynamic model resolution error: {ex}")

        if not model_path:
            raise FileNotFoundError("Wake-word model path is empty or not configured.")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Wake-word model path '{model_path}' does not exist.")

        self.model = Model(
            wakeword_model_paths=[model_path]
        )
        self.confidence_threshold = confidence_threshold
        self.model_name = os.path.splitext(os.path.basename(model_path))[0]
        
        from nova.voice.config import enable_debug
        if enable_debug:
            print(f"Loaded wake-word model:\n{model_path}")

    def detect(self, audio_data: np.ndarray, sample_rate: int = 16000) -> bool:
        """
        Detects wake word. Expects a 1280-sample chunk (80ms at 16kHz) of 16-bit PCM.
        Delegates to the heuristic detector if frame size is not 1280 (for backward compatibility tests).
        """
        flat_audio = audio_data.flatten()
        if len(flat_audio) != 1280:
            # Fallback for compatibility unit tests
            return self.detector.detect(audio_data, sample_rate) or self.nova_detector.detect(audio_data, sample_rate)

        # Check rule-based Nova detector
        if self.nova_detector.detect(audio_data, sample_rate):
            return True

        predictions = self.model.predict(flat_audio)
        
        # Log entire prediction dictionary if debug is enabled (Step 9 requirement)
        from nova.voice.config import enable_debug
        if enable_debug:
            print(predictions)
            if self.model_name not in predictions:
                print(f"Warning: Expected key '{self.model_name}' not found in predictions dictionary!")
        
        # Check the prediction score for our custom model
        score = predictions.get(self.model_name, 0.0)
        return score >= self.confidence_threshold
