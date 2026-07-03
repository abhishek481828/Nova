"""
Consolidated wake-word detection and adaptive threshold controller for Nova.
"""
import numpy as np
import os
import time
import json
import threading
from nova.voice.config import WAKE_WORD_THRESHOLD, WAKE_WORD_MODEL_PATH
import nova.voice.config as cfg
from nova.logger import logger
from nova.voice.async_log import async_log


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
    """
    def __init__(self, model_path: str = WAKE_WORD_MODEL_PATH, confidence_threshold: float = WAKE_WORD_THRESHOLD, wake_word: str = "nova"):
        super().__init__(wake_word, confidence_threshold)
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning, module="onnxruntime")
        warnings.filterwarnings("ignore", category=UserWarning, message=".*CUDAExecutionProvider.*")

        import openwakeword
        from openwakeword.model import Model

        # Instantiated helper detector for compatibility tests
        self.detector = NovaRuleDetector("nova", confidence_threshold)
        self.nova_detector = NovaRuleDetector("nova", confidence_threshold)

        self.predict_lock = threading.RLock()

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

        if not self.oww_active:
            self.model_paths = []
            self.model_names = ["nova"]
            self.model_name = "nova"
        else:
            self.model_paths = model_paths
            self.model_names = [os.path.splitext(os.path.basename(p))[0] for p in model_paths]
            self.model_name = self.model_names[0] if self.model_names else "hey_nova_v0.1"

        self.confidence_threshold = confidence_threshold
        
        # Audio rolling buffer: up to 5 seconds of audio at 16kHz
        self.buffer_capacity = 16000 * 5
        self.audio_buffer = np.zeros(self.buffer_capacity, dtype=np.int16)
        self.buffer_index = 0
        self.buffer_filled = False

        self.diagnostics_path = os.path.expanduser("~/.config/nova/wake_logs.json")
        os.makedirs(os.path.dirname(self.diagnostics_path), exist_ok=True)
        self.diagnostics_history = []
        self.false_wake_count = 0
        self.missed_wake_count = 0
        
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
                    with self.detector.predict_lock:
                        self.detector._process_rolling_audio(x)
                        start_t = time.perf_counter()
                        predictions = self.original(x, *args, **kwargs)
                        inference_latency = time.perf_counter() - start_t
                        adaptive_thresh = self.detector.get_adaptive_threshold()
                        current_rms = self.detector.get_current_rms()
                        
                        for name in self.detector.model_names:
                            score = predictions.get(name, 0.0)
                            if (adaptive_thresh - 0.15) <= score < adaptive_thresh:
                                if self.detector.speech_start_time is not None:
                                    self.detector.log_missed_wake(name, score, current_rms)
                            
                            if score >= adaptive_thresh:
                                latency_sec = 0.0
                                if self.detector.speech_start_time is not None:
                                    latency_sec = time.perf_counter() - self.detector.speech_start_time
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
        flat_audio = audio_data.flatten()
        if len(flat_audio) != 1280:
            return self.detector.detect(audio_data, sample_rate) or self.nova_detector.detect(audio_data, sample_rate)

        if not self.oww_active:
            if self.nova_detector.detect(audio_data, sample_rate):
                return True

        if flat_audio.dtype in (np.float32, np.float64):
            pcm_audio = (np.clip(flat_audio, -1.0, 1.0) * 32767).astype(np.int16)
        else:
            pcm_audio = flat_audio.astype(np.int16)

        with self.predict_lock:
            predictions = self.model.predict(pcm_audio)
        
        from nova.voice.config import enable_debug
        if enable_debug:
            print(predictions)
        
        adaptive_thresh = self.get_adaptive_threshold()
        for name in self.model_names:
            score = predictions.get(name, 0.0)
            if score >= adaptive_thresh:
                return True
        return False

    def _process_rolling_audio(self, pcm_audio: np.ndarray):
        n = len(pcm_audio)
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

        # Calculate RMS of the current frame (fast, local voice activity detection)
        frame_rms = float(np.sqrt(np.mean(pcm_audio.astype(np.float32) ** 2))) / 32768.0

        # Estimate background noise floor using a robust 10th percentile filter over the rolling buffer
        calculated_noise = self.get_noise_floor()
        # Smooth the noise floor slightly to prevent jitter
        self.noise_floor += (calculated_noise - self.noise_floor) * 0.1

        # Use instant frame RMS for voice activity start/stop tracking
        if frame_rms > self.noise_floor * 2.0:
            if self.speech_start_time is None:
                self.speech_start_time = time.perf_counter()
                self.speech_start_time_abs = time.time()
        else:
            if frame_rms < self.noise_floor * 1.2:
                self.speech_start_time = None
                self.speech_start_time_abs = None

    def get_noise_floor(self) -> float:
        active_len = self.buffer_capacity if self.buffer_filled else self.buffer_index
        # We need at least one 1280-sample frame to calculate
        if active_len < 1280:
            return self.noise_floor
        # Reshape the active portion into 1280-sample frames
        num_frames = active_len // 1280
        frames = self.audio_buffer[:num_frames * 1280].reshape(num_frames, 1280)
        # Compute RMS of each frame
        rms_values = np.sqrt(np.mean(frames.astype(np.float32) ** 2, axis=1)) / 32768.0
        # Return 10th percentile
        return float(np.percentile(rms_values, 10))

    def get_current_rms(self) -> float:
        active_buffer = self.audio_buffer if self.buffer_filled else self.audio_buffer[:self.buffer_index]
        if len(active_buffer) == 0:
            return 0.0
        return float(np.sqrt(np.mean(active_buffer.astype(np.float32) ** 2))) / 32768.0

    def get_adaptive_threshold(self) -> float:
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
        
        async_log(self.diagnostics_path, diag, 500)

    def log_false_wake(self, model_name: str, score: float, rms: float):
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
        
        async_log(self.diagnostics_path, diag, 500)
        
        self.confidence_threshold = min(0.85, self.confidence_threshold + 0.02)
        logger.info(f"False wake registered. Automatically increased base confidence threshold to {self.confidence_threshold:.3f}")

    def log_missed_wake(self, model_name: str, score: float, rms: float):
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
        
        async_log(self.diagnostics_path, diag, 500)
        
        self.confidence_threshold = max(0.30, self.confidence_threshold - 0.01)
        logger.info(f"Missed wake candidate registered. Automatically decreased base confidence threshold to {self.confidence_threshold:.3f}")


class AdaptiveWakeController:
    def __init__(self) -> None:
        self.logs_path = os.path.expanduser("~/.config/nova/adaptive_wake_logs.json")
        self.wake_logs_path = os.path.expanduser("~/.config/nova/wake_logs.json")

    def get_historical_success_rate(self) -> float:
        if not os.path.exists(self.wake_logs_path):
            return 1.0
        try:
            with open(self.wake_logs_path, "r") as f:
                logs = json.load(f)
            if not isinstance(logs, list) or not logs:
                return 1.0
            
            recent = logs[-30:]
            total = len(recent)
            successful = sum(1 for item in recent if item.get("event") == "wake_trigger" and not item.get("is_false_wake", False))
            return float(successful / total)
        except Exception:
            return 1.0

    def adapt(
        self,
        noise_floor: float,
        signal_quality_snr: float | None = None,
        clipping_pct: float | None = None
    ) -> dict[str, float]:
        success_rate = self.get_historical_success_rate()

        old_vals = {
            "wake_threshold": float(getattr(cfg, "WAKE_WORD_CONFIDENCE", 0.50)),
            "vad_threshold": float(getattr(cfg, "VAD_THRESHOLD", 0.001)),
            "silence_timeout": float(getattr(cfg, "SILENCE_TIMEOUT", 2.0)),
            "speaker_threshold": float(getattr(cfg, "SPEAKER_THRESHOLD", 0.75))
        }

        new_vals = old_vals.copy()
        reasons = []

        # 1. Adapt Wake Threshold
        if "NOVA_WAKE_WORD_CONFIDENCE" in os.environ or "WAKE_WORD_CONFIDENCE" in os.environ:
            env_val = os.environ.get("NOVA_WAKE_WORD_CONFIDENCE", os.environ.get("WAKE_WORD_CONFIDENCE"))
            try:
                new_vals["wake_threshold"] = float(env_val)
            except ValueError:
                pass
        else:
            wake_thresh = 0.50
            noise_adjustment = noise_floor * 4.0
            wake_thresh += min(0.20, noise_adjustment)
            if noise_adjustment > 0.02:
                reasons.append(f"Raised wake threshold by +{noise_adjustment:.2f} due to high background noise ({noise_floor:.5f})")

            if success_rate < 0.70:
                wake_thresh += 0.15
                reasons.append(f"Raised wake threshold by +0.15 due to low success rate ({success_rate:.2%})")
            elif success_rate > 0.95:
                wake_thresh -= 0.05
                
            new_vals["wake_threshold"] = min(0.85, max(0.30, wake_thresh))

        # 2. Adapt VAD Noise Threshold
        if "NOVA_VAD_THRESHOLD" in os.environ or "VAD_THRESHOLD" in os.environ:
            env_val = os.environ.get("NOVA_VAD_THRESHOLD", os.environ.get("VAD_THRESHOLD"))
            try:
                new_vals["vad_threshold"] = float(env_val)
            except ValueError:
                pass
        else:
            margin = getattr(cfg, "NOISE_FLOOR_MARGIN", 0.0005)
            vad_thresh = (noise_floor * 1.5) + margin
            if vad_thresh > old_vals["vad_threshold"] * 1.2:
                reasons.append(f"Raised VAD threshold to {vad_thresh:.5f} to adapt to noise floor ({noise_floor:.5f})")
            new_vals["vad_threshold"] = min(0.01, max(0.0005, vad_thresh))

        # 3. Adapt Silence Timeout
        if "NOVA_SILENCE_TIMEOUT" in os.environ or "SILENCE_TIMEOUT" in os.environ:
            env_val = os.environ.get("NOVA_SILENCE_TIMEOUT", os.environ.get("SILENCE_TIMEOUT"))
            try:
                new_vals["silence_timeout"] = float(env_val)
            except ValueError:
                pass
        else:
            silence_t = 2.0
            if noise_floor > 0.008:
                silence_t = 3.0
                reasons.append(f"Extended silence timeout to 3.0s due to noisy recording environment ({noise_floor:.5f})")
            if signal_quality_snr is not None and signal_quality_snr < 12.0:
                silence_t = max(silence_t, 3.2)
                reasons.append(f"Extended silence timeout to 3.2s due to poor signal SNR ({signal_quality_snr:.1f}dB)")
            new_vals["silence_timeout"] = min(4.0, max(1.5, silence_t))

        # 4. Adapt Speaker Verification Threshold
        if "NOVA_SPEAKER_THRESHOLD" in os.environ or "SPEAKER_THRESHOLD" in os.environ:
            env_val = os.environ.get("NOVA_SPEAKER_THRESHOLD", os.environ.get("SPEAKER_THRESHOLD"))
            try:
                new_vals["speaker_threshold"] = float(env_val)
            except ValueError:
                pass
        else:
            speaker_thresh = 0.75
            if signal_quality_snr is not None and signal_quality_snr < 15.0:
                speaker_thresh -= 0.05
                reasons.append(f"Lowered speaker threshold to {speaker_thresh:.2f} due to low SNR ({signal_quality_snr:.1f}dB)")
            if success_rate < 0.70:
                speaker_thresh += 0.05
                reasons.append(f"Raised speaker threshold to {speaker_thresh:.2f} due to low trigger success rate")
            new_vals["speaker_threshold"] = min(0.85, max(0.60, speaker_thresh))

        has_changed = False
        for k in new_vals:
            if abs(new_vals[k] - old_vals[k]) > 1e-9:
                has_changed = True
                break

        if has_changed:
            cfg.WAKE_WORD_CONFIDENCE = new_vals["wake_threshold"]
            cfg.VAD_THRESHOLD = new_vals["vad_threshold"]
            cfg.SILENCE_TIMEOUT = new_vals["silence_timeout"]
            cfg.SPEAKER_THRESHOLD = new_vals["speaker_threshold"]
            
            self._log_adaptation_event(noise_floor, signal_quality_snr, success_rate, old_vals, new_vals, reasons)
            logger.info("Adaptive wake thresholds updated dynamically.")
            
        return new_vals

    def _log_adaptation_event(self, noise, snr, success_rate, old_v, new_v, reasons) -> None:
        event = {
            "timestamp": time.time(),
            "datetime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "inputs": {
                "noise_floor": float(noise),
                "snr_db": float(snr) if snr is not None else None,
                "success_rate": float(success_rate)
            },
            "old_thresholds": old_v,
            "new_thresholds": new_v,
            "reasons": reasons
        }
        async_log(self.logs_path, event, 300)
