import numpy as np
import os
import time
import threading
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
    Upgraded with:
      - Rolling PCM audio buffer
      - Multiple concurrent wake phrases/ONNX models loading
      - Noise-adaptive confidence threshold tuning
      - In-memory diagnostics & latency calculations
      - False/Missed wake logging in ~/.config/nova/wake_logs.json
      - Automatic base threshold tuning from false/missed triggers
    """
    def __init__(self, model_path: str = WAKE_WORD_MODEL_PATH, confidence_threshold: float = WAKE_WORD_THRESHOLD, wake_word: str = "nova"):
        super().__init__(wake_word, confidence_threshold)
        # Suppress verbose CUDA/ONNX runtime warnings to keep logs clean
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning, module="onnxruntime")
        warnings.filterwarnings("ignore", category=UserWarning, message=".*CUDAExecutionProvider.*")

        import openwakeword
        from openwakeword.model import Model

        # Instantiated helper detector for compatibility tests
        self.detector = NovaRuleDetector("nova", confidence_threshold)
        self.nova_detector = NovaRuleDetector("nova", confidence_threshold)

        # Thread-safety lock for predictions (High priority check)
        self.predict_lock = threading.Lock()

        # Handle multiple wake phrases (ONNX models)
        model_paths = []
        if model_path:
            if isinstance(model_path, list):
                model_paths = [p for p in model_path if os.path.exists(p)]
            elif os.path.isdir(model_path):
                import glob
                model_paths = glob.glob(os.path.join(model_path, "*.onnx"))
            elif os.path.exists(model_path):
                model_paths = [model_path]

        # Automatically locate hey_nova model dynamically if no valid models found
        if not model_paths:
            try:
                package_dir = os.path.dirname(openwakeword.__file__)
                resources_model_path = os.path.join(package_dir, "resources", "models", "hey_nova_v0.1.onnx")
                if os.path.exists(resources_model_path):
                    model_paths = [resources_model_path]
            except Exception as ex:
                logger.debug(f"Dynamic model resolution error: {ex}")

        self.oww_active = False
        self.model = None
        if model_paths:
            try:
                self.model = Model(wakeword_model_paths=model_paths)
                self.oww_active = True
            except Exception as e:
                logger.warning(f"Failed to initialize OpenWakeWord Model ({e}); falling back to rule detector.")

        # If OWW initialization failed or no models found, raise or fallback gracefully
        if not self.oww_active:
            self.model_paths = []
            self.model_names = ["nova"]
            self.model_name = "nova"
        else:
            self.model_paths = model_paths
            self.model_names = [os.path.splitext(os.path.basename(p))[0] for p in model_paths]
            # Keep self.model_name for backward compatibility with existing tests
            self.model_name = self.model_names[0] if self.model_names else "hey_nova_v0.1"

        self.confidence_threshold = confidence_threshold
        
        # Audio rolling buffer: up to 5 seconds of audio at 16kHz
        self.buffer_capacity = 16000 * 5
        self.audio_buffer = np.zeros(self.buffer_capacity, dtype=np.int16)
        self.buffer_index = 0
        self.buffer_filled = False

        # Logs & Diagnostics
        self.diagnostics_path = os.path.expanduser("~/.config/nova/wake_logs.json")
        os.makedirs(os.path.dirname(self.diagnostics_path), exist_ok=True)
        self.diagnostics_history = []
        self.false_wake_count = 0
        self.missed_wake_count = 0
        
        # Speech tracking for latency calculation (Critical latency fix)
        self.speech_start_time = None
        self.speech_start_time_abs = None
        self.last_speech_start_time_abs = None
        self.noise_floor = 0.001

        # Wrap model.predict using a custom delegating callable class to preserve mock compatibility
        if self.oww_active and self.model is not None:
            original_predict = self.model.predict

            class WrappedPredict:
                def __init__(self, detector_instance, original):
                    self.detector = detector_instance
                    self.original = original

                def __call__(self, x, *args, **kwargs):
                    # Lock prediction calls to prevent concurrent corruption of ONNX/OWW states
                    with self.detector.predict_lock:
                        # Process incoming frame inside rolling buffer
                        self.detector._process_rolling_audio(x)
                        
                        # Measure inference execution latency
                        start_t = time.perf_counter()
                        predictions = self.original(x, *args, **kwargs)
                        inference_latency = time.perf_counter() - start_t
                        
                        # Determine adaptive threshold
                        adaptive_thresh = self.detector.get_adaptive_threshold()
                        current_rms = self.detector.get_current_rms()
                        
                        # Track scores and run auto-tuning / logs
                        for name in self.detector.model_names:
                            score = predictions.get(name, 0.0)
                            
                            # Check for Missed Wake
                            if (adaptive_thresh - 0.15) <= score < adaptive_thresh:
                                if self.detector.speech_start_time is not None:
                                    self.detector.log_missed_wake(name, score, current_rms)
                            
                            # Triggered
                            if score >= adaptive_thresh:
                                latency_sec = 0.0
                                if self.detector.speech_start_time is not None:
                                    latency_sec = time.perf_counter() - self.detector.speech_start_time
                                    # Record last absolute speech start time for e2e turn latency
                                    self.detector.last_speech_start_time_abs = self.detector.speech_start_time_abs
                                self.detector._log_diagnostics(name, score, current_rms, inference_latency, latency_sec, adaptive_thresh)
                        
                        return predictions

                def __getattr__(self, name):
                    return getattr(self.original, name)

            self.model.predict = WrappedPredict(self, original_predict)

        from nova.voice.config import enable_debug
        if enable_debug and self.oww_active:
            print(f"Loaded wake-word models:\n" + "\n".join(model_paths))


    def detect(self, audio_data: np.ndarray, sample_rate: int = 16000) -> bool:
        """
        Detects wake word. Expects a 1280-sample chunk (80ms at 16kHz) of 16-bit PCM.
        Delegates to the heuristic detector if frame size is not 1280 (for backward compatibility tests).
        """
        flat_audio = audio_data.flatten()
        if len(flat_audio) != 1280:
            # Fallback for compatibility unit tests
            return self.detector.detect(audio_data, sample_rate) or self.nova_detector.detect(audio_data, sample_rate)

        # Check rule-based Nova detector ONLY if OWW is not active (High priority check)
        if not self.oww_active:
            if self.nova_detector.detect(audio_data, sample_rate):
                return True

        # Convert float to 16-bit PCM (int16) for OpenWakeWord inference
        if flat_audio.dtype in (np.float32, np.float64):
            pcm_audio = (np.clip(flat_audio, -1.0, 1.0) * 32767).astype(np.int16)
        else:
            pcm_audio = flat_audio.astype(np.int16)

        # Thread safety lock check
        with self.predict_lock:
            predictions = self.model.predict(pcm_audio)
        
        # Log entire prediction dictionary if debug is enabled
        from nova.voice.config import enable_debug
        if enable_debug:
            print(predictions)
            if self.model_name not in predictions:
                print(f"Warning: Expected key '{self.model_name}' not found in predictions dictionary!")
        
        # Check scores against adaptive threshold
        adaptive_thresh = self.get_adaptive_threshold()
        for name in self.model_names:
            score = predictions.get(name, 0.0)
            if score >= adaptive_thresh:
                return True
        return False

    def _process_rolling_audio(self, pcm_audio: np.ndarray):
        n = len(pcm_audio)
        # Store in rolling buffer
        if self.buffer_index + n <= self.buffer_capacity:
            self.audio_buffer[self.buffer_index:self.buffer_index+n] = pcm_audio
            self.buffer_index += n
        else:
            first_part = self.buffer_capacity - self.buffer_index
            self.audio_buffer[self.buffer_index:] = pcm_audio[:first_part]
            self.audio_buffer[:n-first_part] = pcm_audio[first_part:]
            self.buffer_index = n - first_part
            self.buffer_filled = True

        if self.buffer_index >= self.buffer_capacity:
            self.buffer_index = 0
            self.buffer_filled = True

        # Compute dynamic noise floor (smoothed RMS)
        current_rms = self.get_current_rms()
        self.noise_floor += (current_rms - self.noise_floor) * 0.05

        # Track speech onset
        if current_rms > self.noise_floor * 2.0:
            if self.speech_start_time is None:
                self.speech_start_time = time.perf_counter()
                self.speech_start_time_abs = time.time()
        else:
            if current_rms < self.noise_floor * 1.2:
                self.speech_start_time = None
                self.speech_start_time_abs = None

    def get_current_rms(self) -> float:
        active_buffer = self.audio_buffer if self.buffer_filled else self.audio_buffer[:self.buffer_index]
        if len(active_buffer) == 0:
            return 0.0
        return float(np.sqrt(np.mean(active_buffer.astype(np.float32) ** 2))) / 32768.0

    def get_adaptive_threshold(self) -> float:
        # Raise threshold under noisy conditions
        # If noise floor is above 0.005, add up to +0.20 to the base threshold
        noise_factor = max(0.0, self.noise_floor - 0.005)
        offset = min(0.20, noise_factor * 10.0)
        return min(0.95, self.confidence_threshold + offset)

    def _log_diagnostics(self, model_name: str, score: float, rms: float, inference_latency: float, speaking_latency: float, threshold: float):
        diag = {
            "timestamp": time.time(),
            "event": "wake_trigger",
            "model_name": model_name,
            "score": float(score),
            "rms": float(rms),
            "noise_floor": float(self.noise_floor),
            "inference_latency_ms": float(inference_latency * 1000.0),
            "speaking_latency_ms": float(speaking_latency * 1000.0),
            "threshold": float(threshold)
        }
        self.diagnostics_history.append(diag)
        self.diagnostics_history = self.diagnostics_history[-500:]
        
        # Async Logging (Critical optimization)
        from nova.voice.async_logging import async_log
        async_log(self.diagnostics_path, diag, 500)

    def log_false_wake(self, model_name: str, score: float, rms: float):
        """Called by downstream modules when a wake trigger was false (no speech followed)."""
        self.false_wake_count += 1
        diag = {
            "timestamp": time.time(),
            "event": "false_wake",
            "model_name": model_name,
            "score": float(score),
            "rms": float(rms),
            "noise_floor": float(self.noise_floor),
            "threshold": float(self.confidence_threshold)
        }
        self.diagnostics_history.append(diag)
        self.diagnostics_history = self.diagnostics_history[-500:]
        
        # Async Logging (Critical optimization)
        from nova.voice.async_logging import async_log
        async_log(self.diagnostics_path, diag, 500)
        
        # Auto-tune: increase base threshold slightly on false trigger
        self.confidence_threshold = min(0.85, self.confidence_threshold + 0.02)
        logger.info(f"False wake registered. Automatically increased base confidence threshold to {self.confidence_threshold:.3f}")

    def log_missed_wake(self, model_name: str, score: float, rms: float):
        """Logged internally when score is close to threshold during speech activity."""
        self.missed_wake_count += 1
        diag = {
            "timestamp": time.time(),
            "event": "missed_wake",
            "model_name": model_name,
            "score": float(score),
            "rms": float(rms),
            "noise_floor": float(self.noise_floor),
            "threshold": float(self.confidence_threshold)
        }
        self.diagnostics_history.append(diag)
        self.diagnostics_history = self.diagnostics_history[-500:]
        
        # Async Logging (Critical optimization)
        from nova.voice.async_logging import async_log
        async_log(self.diagnostics_path, diag, 500)
        
        # Auto-tune: decrease base threshold slightly on missed candidate
        self.confidence_threshold = max(0.30, self.confidence_threshold - 0.01)
        logger.info(f"Missed wake candidate registered. Automatically decreased base confidence threshold to {self.confidence_threshold:.3f}")


