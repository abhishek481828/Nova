"""
Audio processing pipeline for the Nova Voice subsystem.

Pipeline (in order):
  DC Offset Removal  →  High-pass Filter (Butterworth, stateful)  →
  RNNoise denoising  →  AGC  →  WebRTC VAD

All classes are designed to be instantiated once per recording session
and called on successive 30 ms chunks (480 samples at 16 kHz).
"""

import os
import time
import ctypes
import ctypes.util
import numpy as np
from nova.voice.config import (
    SAMPLE_RATE, CHANNELS, HIGHPASS_CUTOFF, VAD_AGGRESSIVENESS,
    VAD_THRESHOLD, NOISE_FLOOR_MARGIN,
    AGC_TARGET_RMS, AGC_MAX_GAIN, AGC_RATE, enable_debug,
)
from nova.logger import logger

try:
    from scipy.signal import resample_poly
except ImportError:
    resample_poly = None


# ---------------------------------------------------------------------------
# Resampling helpers (used by RNNoise 48 kHz ↔ 16 kHz bridge)
# ---------------------------------------------------------------------------

def resample_16k_to_48k(data_16k: np.ndarray) -> np.ndarray:
    """
    Resample a 16 kHz array to 48 kHz using polyphase anti-aliased filter.
    Falls back to linear interpolation if scipy is unavailable.
    """
    flat = data_16k.flatten().astype(np.float32)
    if resample_poly is not None:
        try:
            return resample_poly(flat, up=3, down=1).astype(np.float32)
        except Exception:
            pass
    
    xp = np.arange(len(flat))
    x  = np.linspace(0, len(flat) - 1, len(flat) * 3)
    return np.interp(x, xp, flat).astype(np.float32)


def resample_48k_to_16k(data_48k: np.ndarray) -> np.ndarray:
    """
    Resample a 48 kHz array to 16 kHz using polyphase anti-aliased filter.
    Falls back to linear interpolation if scipy is unavailable.
    """
    flat = data_48k.flatten().astype(np.float32)
    if resample_poly is not None:
        try:
            return resample_poly(flat, up=1, down=3).astype(np.float32)
        except Exception:
            pass

    xp = np.arange(len(flat))
    x  = np.linspace(0, len(flat) - 1, len(flat) // 3)
    return np.interp(x, xp, flat).astype(np.float32)


# ---------------------------------------------------------------------------
# RNNoise
# ---------------------------------------------------------------------------

class RNNoiseWrapper:
    """
    Ctypes wrapper for real-time speech denoising via the RNNoise library.
    Gracefully bypasses if librnnoise is not found.

    FIX: output is now explicitly cast to float32 (was float64 previously).
    """

    def __init__(self):
        self.lib   = None
        self.state = None

        # Locate native library: try ctypes.util first, then LD_LIBRARY_PATH
        lib_name = ctypes.util.find_library("rnnoise")
        if not lib_name:
            for path in os.environ.get("LD_LIBRARY_PATH", "").split(":"):
                for name in ("librnnoise.so", "librnnoise.so.0", "librnnoise.so.0.4.1"):
                    full_path = os.path.join(path, name)
                    if os.path.exists(full_path):
                        lib_name = full_path
                        break
                if lib_name:
                    break
        if not lib_name:
            lib_name = "librnnoise.so.0"

        try:
            self.lib = ctypes.CDLL(lib_name)
            self.lib.rnnoise_create.restype         = ctypes.c_void_p
            self.lib.rnnoise_create.argtypes        = [ctypes.c_void_p]
            self.lib.rnnoise_destroy.restype        = None
            self.lib.rnnoise_destroy.argtypes       = [ctypes.c_void_p]
            self.lib.rnnoise_process_frame.restype  = ctypes.c_float
            self.lib.rnnoise_process_frame.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_float),
                ctypes.POINTER(ctypes.c_float),
            ]
            self.state = self.lib.rnnoise_create(None)
        except Exception as e:
            logger.debug(f"RNNoise shared library not available: {e}")
            self.lib  = None
            self.state = None

    def is_available(self) -> bool:
        return self.state is not None

    def denoise_frame(self, frame_160_samples: np.ndarray) -> np.ndarray:
        """
        Denoise a 10 ms frame (160 samples at 16 kHz).
        Upsamples → RNNoise (48 kHz) → downsample → returns float32.
        Uses C pointers directly to avoid python object unpacking overhead.
        """
        if not self.is_available():
            return frame_160_samples.astype(np.float32)

        try:
            audio_48k        = resample_16k_to_48k(frame_160_samples)
            audio_48k_scaled = (audio_48k * 32768.0).astype(np.float32)

            out_array = np.zeros(480, dtype=np.float32)

            in_ptr  = audio_48k_scaled.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            out_ptr = out_array.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

            self.lib.rnnoise_process_frame(self.state, out_ptr, in_ptr)

            denoised_48k = out_array / 32768.0
            result = resample_48k_to_16k(denoised_48k)
            return result.reshape(frame_160_samples.shape).astype(np.float32)
        except Exception as e:
            logger.debug(f"RNNoise processing error: {e}")
            return frame_160_samples.astype(np.float32)

    def denoise_chunk(self, chunk_480_samples: np.ndarray) -> np.ndarray:
        """
        Denoise a 30 ms chunk (480 samples at 16 kHz) in a single block.
        Upsamples entire 480-sample block to 1440 samples (48 kHz) at once,
        runs RNNoise 3 times on the contiguous float array offsets,
        and downsamples the 1440-sample result back to 480 samples at once.
        Supports arbitrary input size by padding to the nearest multiple of 480 samples.
        """
        if len(chunk_480_samples) == 0:
            return chunk_480_samples.astype(np.float32)

        if not self.is_available():
            return chunk_480_samples.astype(np.float32)

        original_shape = chunk_480_samples.shape
        flat_audio = chunk_480_samples.flatten()
        original_len = len(flat_audio)
        
        # Pad to multiple of 480 samples
        if original_len % 480 != 0:
            pad_len = 480 - (original_len % 480)
            flat_audio = np.pad(flat_audio, (0, pad_len), mode="constant").astype(np.float32)
        
        try:
            n_blocks = len(flat_audio) // 480
            audio_48k        = resample_16k_to_48k(flat_audio)
            audio_48k_scaled = (audio_48k * 32768.0).astype(np.float32)

            out_array = np.zeros(n_blocks * 1440, dtype=np.float32)

            # Process 10ms (480-sample at 48kHz) contiguous blocks in C
            for i in range(n_blocks * 3):
                offset = i * 480
                in_slice = audio_48k_scaled[offset:offset+480]
                out_slice = out_array[offset:offset+480]
                
                in_ptr_offset  = in_slice.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
                out_ptr_offset = out_slice.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

                self.lib.rnnoise_process_frame(self.state, out_ptr_offset, in_ptr_offset)

            denoised_48k = out_array / 32768.0
            result = resample_48k_to_16k(denoised_48k)
            # Crop to original length
            result_cropped = result[:original_len]
            return result_cropped.reshape(original_shape).astype(np.float32)
        except Exception as e:
            logger.debug(f"RNNoise chunk processing error: {e}")
            return chunk_480_samples.astype(np.float32)

    def destroy(self):
        if self.lib and self.state:
            try:
                self.lib.rnnoise_destroy(self.state)
            except Exception:
                pass
            self.state = None


# ---------------------------------------------------------------------------
# High-pass Filter (stateful — maintains continuity across chunks)
# ---------------------------------------------------------------------------

class HighPassFilter:
    """
    5th-order Butterworth high-pass filter removing low-frequency noise
    (fan hum, AC hum, desk vibration) below HIGHPASS_CUTOFF Hz.
    Validates cutoff limit to support any sampling rates.
    """

    def __init__(self, cutoff: float = HIGHPASS_CUTOFF, fs: float = SAMPLE_RATE):
        self.cutoff = cutoff
        self.fs = fs
        self.sos = None
        self._zi = None

        nyq = 0.5 * fs
        if 0 < cutoff < nyq:
            try:
                from scipy.signal import butter, sosfilt_zi
                normal_cutoff = cutoff / nyq
                # Use second-order sections (numerically more stable than ba form)
                self.sos = butter(5, normal_cutoff, btype="high", analog=False, output="sos")
                # Persistent filter state — updated after every chunk
                self._zi = sosfilt_zi(self.sos)   # shape: (n_sections, 2)
            except Exception as e:
                logger.warning(f"High-pass filter initialization failed: {e}. Filter will be bypassed.")
        else:
            logger.warning(f"Invalid high-pass cutoff {cutoff} for sample rate {fs}. Filter will be bypassed.")

    def process(self, chunk: np.ndarray) -> np.ndarray:
        """
        Filter one chunk in-place, preserving filter state across calls.
        Returns same shape as input. Bypasses if configuration is invalid.
        """
        if self.sos is None or self._zi is None:
            return chunk.astype(np.float32)

        try:
            from scipy.signal import sosfilt
            flat = chunk.flatten().astype(np.float32)
            filtered, self._zi = sosfilt(self.sos, flat, zi=self._zi)
            return filtered.reshape(chunk.shape).astype(np.float32)
        except Exception as e:
            logger.debug(f"High-pass filter processing error: {e}")
            return chunk.astype(np.float32)


# ---------------------------------------------------------------------------
# Automatic Gain Control (RMS-based, with anti-clipping limiter)
# ---------------------------------------------------------------------------

class AutomaticGainControl:
    """
    Automatic Gain Control normalising input audio to a target RMS level.
    Freezes gain adaptation during silent gaps to prevent noise pumping.
    """

    def __init__(
        self,
        target_rms:  float = AGC_TARGET_RMS,
        max_gain:    float = AGC_MAX_GAIN,
        rate:        float = AGC_RATE,
        target_level: float | None = None,
        noise_floor: float = 0.002,
    ):
        self.target_rms  = target_level if target_level is not None else target_rms
        self.max_gain    = max_gain
        self.rate        = rate
        self.noise_floor = noise_floor
        self.current_gain = 1.0

    def process(self, chunk: np.ndarray, speech_active: bool = True) -> np.ndarray:
        if len(chunk) == 0:
            return chunk.astype(np.float32)

        flat = chunk.flatten().astype(np.float32)

        # RMS-based gain calculation
        rms = float(np.sqrt(np.mean(flat * flat)))
        if rms > 1e-6:
            # Prevent noise pumping: only adapt gain if speech is active and signal is above noise gate
            if speech_active and (rms > self.noise_floor * 1.5):
                target_gain = min(self.target_rms / rms, self.max_gain)
                # Exponential moving average for smooth gain transitions
                self.current_gain += (target_gain - self.current_gain) * self.rate

        amplified = flat * self.current_gain

        # Anti-clipping: Transparent soft-knee limiter for values above 0.9
        output = amplified.copy()
        abs_output = np.abs(output)
        over_mask = abs_output > 0.9
        if np.any(over_mask):
            sgn = np.sign(output[over_mask])
            val = abs_output[over_mask]
            output[over_mask] = sgn * (0.9 + 0.1 * np.tanh((val - 0.9) / 0.1))

        # Calculate metrics for logging
        out_rms = float(np.sqrt(np.mean(output * output)))
        out_peak = float(np.max(np.abs(output)))
        clipping_pct = float(np.sum(np.abs(output) >= 0.99) / len(output) * 100.0) if len(output) > 0 else 0.0

        if enable_debug:
            msg = f"[DBG AGC] rms={out_rms:.4f} peak={out_peak:.4f} clipping={clipping_pct:.2f}% gain={self.current_gain:.4f}"
            print(msg)
            logger.debug(msg)

        return output.reshape(chunk.shape).astype(np.float32)


# ---------------------------------------------------------------------------
# WebRTC Voice Activity Detector
# ---------------------------------------------------------------------------

class WebRTCVoiceActivityDetector:
    """
    Google WebRTC VAD. Falls back to simple RMS-energy VAD if webrtcvad is not installed.
    Supports hangover time to prevent syllable flicker, and handles arbitrary chunk sizes.
    """

    def __init__(
        self,
        aggressiveness:    int   = VAD_AGGRESSIVENESS,
        default_threshold: float = VAD_THRESHOLD,
        hangover_frames:   int   = 8,
    ):
        self.vad = None
        self.default_threshold = default_threshold
        self.hangover_frames = hangover_frames
        self.hangover_counter = 0
        try:
            import webrtcvad
            self.vad = webrtcvad.Vad(aggressiveness)
        except Exception as e:
            logger.debug(f"WebRTC VAD not installed: {e}")

    def is_available(self) -> bool:
        return self.vad is not None

    def is_speech(self, frame_float: np.ndarray, sample_rate: int) -> bool:
        if not self.is_available():
            rms = float(np.sqrt(np.mean(np.square(frame_float))))
            raw_speech = rms >= self.default_threshold
            return self._apply_hangover(raw_speech)

        flat = frame_float.flatten()
        frame_len = len(flat)
        samples_per_10ms = sample_rate // 100

        # Check if frame is a standard 10, 20, or 30 ms size
        is_valid_size = (frame_len in (samples_per_10ms, samples_per_10ms * 2, samples_per_10ms * 3))

        if is_valid_size:
            frame_int16 = (flat * 32767).astype(np.int16)
            try:
                raw_speech = self.vad.is_speech(frame_int16.tobytes(), sample_rate)
                return self._apply_hangover(raw_speech)
            except Exception as e:
                logger.debug(f"WebRTC VAD error: {e}")
                rms = float(np.sqrt(np.mean(np.square(frame_float))))
                raw_speech = rms >= self.default_threshold
                return self._apply_hangover(raw_speech)

        # Non-standard frame size: chunk it into 10ms blocks to prevent crashes
        block_size = samples_per_10ms
        n_blocks = (frame_len + block_size - 1) // block_size
        detected_speech = False

        try:
            for i in range(n_blocks):
                offset = i * block_size
                block = flat[offset:offset+block_size]
                if len(block) < block_size:
                    block = np.pad(block, (0, block_size - len(block)), mode="constant")
                
                block_int16 = (block * 32767).astype(np.int16)
                if self.vad.is_speech(block_int16.tobytes(), sample_rate):
                    detected_speech = True
                    break
            return self._apply_hangover(detected_speech)
        except Exception as e:
            logger.debug(f"Chunked WebRTC VAD error: {e}")
            rms = float(np.sqrt(np.mean(np.square(frame_float))))
            raw_speech = rms >= self.default_threshold
            return self._apply_hangover(raw_speech)

    def _apply_hangover(self, raw_speech: bool) -> bool:
        if raw_speech:
            self.hangover_counter = self.hangover_frames
            return True
        else:
            if self.hangover_counter > 0:
                self.hangover_counter -= 1
                return True
            return False


# ---------------------------------------------------------------------------
# Ambient Calibrator
# ---------------------------------------------------------------------------

class AmbientCalibrator:
    """
    Records ambient noise for AMBIENT_CALIBRATION_DURATION seconds at startup
    and derives noise floor + speech threshold automatically.
    Uses percentile-based sorting to resist transient mouse clicks or breaths.
    """

    def __init__(self):
        self.noise_floor       = 0.001
        self.speech_threshold  = VAD_THRESHOLD
        self.silence_threshold = VAD_THRESHOLD * 0.5

    def calibrate(self, ambient_audio: np.ndarray, frame_size: int = 480) -> None:
        if len(ambient_audio) == 0:
            return
        flat = ambient_audio.flatten().astype(np.float32)
        n_frames = len(flat) // frame_size

        if n_frames >= 5:
            frame_rms = []
            for i in range(n_frames):
                frame = flat[i * frame_size:(i + 1) * frame_size]
                frame_rms.append(float(np.sqrt(np.mean(frame * frame))))
            
            # 10th percentile of frame energies (rejects clicking spikes)
            frame_rms.sort()
            idx = max(0, int(len(frame_rms) * 0.1))
            rms = frame_rms[idx]
        else:
            rms = float(np.sqrt(np.mean(flat * flat)))

        self.noise_floor       = rms
        self.speech_threshold  = rms + NOISE_FLOOR_MARGIN
        self.silence_threshold = rms + (NOISE_FLOOR_MARGIN * 0.5)
        logger.info(
            f"Microphone Calibrated — "
            f"Noise Floor (10th percentile): {self.noise_floor:.5f} | "
            f"Speech Threshold: {self.speech_threshold:.5f}"
        )


# ---------------------------------------------------------------------------
# Audio Diagnostics
# ---------------------------------------------------------------------------

class AudioDiagnostics:
    """
    Measures audio quality metrics on a chunk or full recording.

    Metrics:
      rms          — root mean square energy
      peak         — peak absolute amplitude
      noise_floor  — estimated noise floor (RMS of quietest 10% of frames)
      clipping_pct — percentage of samples within 1% of ±1.0
      snr_db       — estimated signal-to-noise ratio in dB
      speech_dur_s — estimated speech duration in seconds (VAD-gated)

    Warnings are printed automatically when thresholds are exceeded.
    """

    # Thresholds for automatic warnings
    CLIPPING_WARN_PCT  = 0.5    # warn if >0.5% of samples are clipping
    RMS_TOO_QUIET      = 0.002  # warn if RMS below this level
    NOISE_FLOOR_HIGH   = 0.05   # warn if noise floor is unusually high
    SNR_WARN_DB        = 10.0   # warn if SNR < 10 dB

    def __init__(self, sample_rate: int = SAMPLE_RATE, frame_size: int = 480):
        self.sample_rate = sample_rate
        self.frame_size  = frame_size

    def measure(self, audio: np.ndarray) -> dict:
        """
        Analyse ``audio`` (float32, 1-D or 2-D mono) and return a metrics dict.
        Also prints warnings for problematic conditions.
        """
        from nova.utils import print_warning

        flat = audio.flatten().astype(np.float32)
        if len(flat) == 0:
            return {}

        rms  = float(np.sqrt(np.mean(flat * flat)))
        peak = float(np.max(np.abs(flat)))

        # Clipping: samples at or beyond 99% of full scale
        clipping_count = int(np.sum(np.abs(flat) >= 0.99))
        clipping_pct   = 100.0 * clipping_count / len(flat)

        # Noise floor: RMS of frames with the lowest 10% energy
        n_frames = len(flat) // self.frame_size
        if n_frames >= 5:
            frame_rms = [
                float(np.sqrt(np.mean(flat[i * self.frame_size:(i + 1) * self.frame_size] ** 2)))
                for i in range(n_frames)
            ]
            frame_rms.sort()
            quietest = frame_rms[: max(1, n_frames // 10)]
            noise_floor = float(np.mean(quietest))
        else:
            noise_floor = rms * 0.3   # fallback estimate

        # SNR estimate (dB)
        if noise_floor > 1e-9:
            snr_db = 20.0 * np.log10(rms / noise_floor) if rms > noise_floor else 0.0
        else:
            snr_db = float("inf")

        # Speech duration estimate: count frames where RMS > 2× noise floor
        speech_frames = 0
        for i in range(n_frames):
            f = flat[i * self.frame_size:(i + 1) * self.frame_size]
            if float(np.sqrt(np.mean(f * f))) > noise_floor * 2.0:
                speech_frames += 1
        speech_dur_s = speech_frames * self.frame_size / self.sample_rate

        metrics = {
            "rms":          rms,
            "peak":         peak,
            "noise_floor":  noise_floor,
            "clipping_pct": clipping_pct,
            "snr_db":       snr_db,
            "speech_dur_s": speech_dur_s,
        }

        # Auto-warnings
        if rms < self.RMS_TOO_QUIET:
            print_warning(
                f"Microphone signal very quiet (RMS={rms:.4f}) — "
                "check microphone gain or move closer."
            )
        if clipping_pct > self.CLIPPING_WARN_PCT:
            print_warning(
                f"Audio clipping detected ({clipping_pct:.1f}% of samples) — "
                "reduce microphone gain."
            )
        if noise_floor > self.NOISE_FLOOR_HIGH:
            print_warning(
                f"High background noise floor ({noise_floor:.4f}) — "
                "consider a quieter environment or enable RNNoise."
            )
        if 0 < snr_db < self.SNR_WARN_DB:
            print_warning(
                f"Low SNR ({snr_db:.1f} dB) — speech may not transcribe reliably."
            )

        return metrics


# ---------------------------------------------------------------------------
# Automatic Microphone Selection
# ---------------------------------------------------------------------------

def select_best_microphone() -> dict | None:
    """
    Query all available input devices and return the one most suitable for
    16 kHz mono speech capture.

    Preference order:
      1. Default input device if it supports 16 kHz mono
      2. First device that supports 16 kHz mono
      3. Default input device regardless

    Returns the sounddevice device-info dict, or None if no input is found.
    """
    try:
        import sounddevice as sd
    except ImportError:
        return None

    try:
        devices   = sd.query_devices()
        default   = sd.query_devices(kind="input")
    except Exception as e:
        logger.debug(f"Microphone query failed: {e}")
        return None

    # Try default first
    if default and default.get("max_input_channels", 0) >= 1:
        try:
            sd.check_input_settings(
                device=default["name"],
                channels=1,
                dtype="float32",
                samplerate=SAMPLE_RATE,
            )
            return default
        except Exception:
            pass   # default doesn't support 16 kHz — try others

    # Scan all devices
    for dev in (devices if isinstance(devices, list) else [devices]):
        if dev.get("max_input_channels", 0) < 1:
            continue
        try:
            sd.check_input_settings(
                device=dev["name"],
                channels=1,
                dtype="float32",
                samplerate=SAMPLE_RATE,
            )
            logger.info(f"Selected microphone: {dev['name']}")
            return dev
        except Exception:
            continue

    # Last resort: return default even if 16 kHz unsupported
    return default


# ---------------------------------------------------------------------------
# Acoustic Echo Cancellation (AEC) Synchronization & Processors
# ---------------------------------------------------------------------------

def get_reference_chunk(chunk_size: int = 480) -> np.ndarray | None:
    """
    Get synchronized reference playback audio chunk corresponding to the current elapsed play time.
    """
    import time
    import nova.voice.config as voice_config
    
    ref_audio = getattr(voice_config, "aec_reference_audio", None)
    start_time = getattr(voice_config, "aec_playback_start_time", None)
    if ref_audio is None or start_time is None:
        return None
        
    elapsed = time.time() - start_time
    offset = int(elapsed * 16000)
    if offset < 0:
        offset = 0
    if offset >= len(ref_audio):
        voice_config.aec_reference_audio = None
        return None
        
    chunk = ref_audio[offset : offset + chunk_size]
    if len(chunk) < chunk_size:
        chunk = np.pad(chunk, (0, chunk_size - len(chunk)), mode="constant")
    return chunk


class SpeexEchoCanceller:
    """
    Ctypes wrapper for libspeexdsp echo cancellation state.
    """
    def __init__(self, frame_size: int = 480, filter_len: int = 3200):
        self.lib = None
        self.state = None
        self.frame_size = frame_size

        # Locate speexdsp library in typical linux paths and ldconfig paths
        lib_name = ctypes.util.find_library("speexdsp")
        if not lib_name:
            for path in os.environ.get("LD_LIBRARY_PATH", "").split(":"):
                for name in ("libspeexdsp.so", "libspeexdsp.so.1", "libspeexdsp.so.1.2.0"):
                    full_path = os.path.join(path, name)
                    if os.path.exists(full_path):
                        lib_name = full_path
                        break
                if lib_name:
                    break
        if not lib_name:
            lib_name = "libspeexdsp.so.1"

        try:
            self.lib = ctypes.CDLL(lib_name)
            self.lib.speex_echo_state_init.restype = ctypes.c_void_p
            self.lib.speex_echo_state_init.argtypes = [ctypes.c_int, ctypes.c_int]
            self.lib.speex_echo_state_destroy.restype = None
            self.lib.speex_echo_state_destroy.argtypes = [ctypes.c_void_p]
            self.lib.speex_echo_cancellation.restype = None
            self.lib.speex_echo_cancellation.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_short),
                ctypes.POINTER(ctypes.c_short),
                ctypes.POINTER(ctypes.c_short)
            ]
            self.state = self.lib.speex_echo_state_init(frame_size, filter_len)
        except Exception as e:
            logger.debug(f"SpeexDSP shared library not available: {e}")
            self.lib = None
            self.state = None

    def is_available(self) -> bool:
        return self.state is not None

    def process(self, rec: np.ndarray, play: np.ndarray) -> np.ndarray:
        if not self.is_available():
            return rec

        rec_flat = rec.flatten()
        play_flat = play.flatten()
        
        # Convert float32 [-1.0, 1.0] to int16 short
        rec_short = (np.clip(rec_flat, -1.0, 1.0) * 32767).astype(np.int16)
        play_short = (np.clip(play_flat, -1.0, 1.0) * 32767).astype(np.int16)
        out_short = np.zeros(self.frame_size, dtype=np.int16)

        try:
            rec_ptr = rec_short.ctypes.data_as(ctypes.POINTER(ctypes.c_short))
            play_ptr = play_short.ctypes.data_as(ctypes.POINTER(ctypes.c_short))
            out_ptr = out_short.ctypes.data_as(ctypes.POINTER(ctypes.c_short))

            self.lib.speex_echo_cancellation(self.state, rec_ptr, play_ptr, out_ptr)
            
            # Convert back to float32
            out_float = out_short.astype(np.float32) / 32768.0
            return out_float.reshape(rec.shape)
        except Exception as e:
            logger.debug(f"Speex AEC processing failed: {e}")
            return rec

    def destroy(self) -> None:
        if self.lib and self.state:
            try:
                self.lib.speex_echo_state_destroy(self.state)
            except Exception:
                pass
            self.state = None


class NLMSEchoCanceller:
    """
    Vectorized Normalized Least Mean Squares (NLMS) adaptive filter in pure NumPy.
    Acts as a highly optimized fallback when libspeexdsp.so is not available.
    """
    def __init__(self, frame_size: int = 480, filter_len: int = 1600, mu: float = 0.05, eps: float = 1e-4):
        self.frame_size = frame_size
        self.filter_len = filter_len
        self.mu = mu
        self.eps = eps
        self.w = np.zeros(filter_len, dtype=np.float32)
        self.x_history = np.zeros(filter_len + frame_size, dtype=np.float32)

    def process(self, rec: np.ndarray, play: np.ndarray) -> np.ndarray:
        rec_flat = rec.flatten().astype(np.float32)
        play_flat = play.flatten().astype(np.float32)

        # Shift history
        self.x_history[:-self.frame_size] = self.x_history[self.frame_size:]
        self.x_history[-self.frame_size:] = play_flat

        out = np.zeros(self.frame_size, dtype=np.float32)

        # Vectorized NLMS weight adaptation loop
        for i in range(self.frame_size):
            x_vec = self.x_history[i : i + self.filter_len]
            y_hat = np.dot(self.w, x_vec)
            err = rec_flat[i] - y_hat
            out[i] = err

            # Update filter coefficients
            norm_x = np.dot(x_vec, x_vec)
            self.w += self.mu * err * x_vec / (norm_x + self.eps)

        return out.reshape(rec.shape)


class AecProcessor:
    """
    Unified Echo Cancellation Processor.
    Tries Speex AEC first, falling back to NumPy NLMS if unavailable.
    """
    def __init__(self, frame_size: int = 480, filter_len: int = 3200):
        self.speex_aec = SpeexEchoCanceller(frame_size, filter_len)
        self.nlms_aec = NLMSEchoCanceller(frame_size, filter_len) if not self.speex_aec.is_available() else None

    def process(self, mic_chunk: np.ndarray) -> np.ndarray:
        # Check if AEC is disabled in configuration
        from nova.voice.config import ENABLE_ECHO_CANCEL
        if not ENABLE_ECHO_CANCEL:
            return mic_chunk

        # Retrieve synchronized playback reference audio chunk
        ref_chunk = get_reference_chunk(len(mic_chunk))
        if ref_chunk is None:
            return mic_chunk

        # Run primary Speex AEC or fallback NLMS
        if self.speex_aec.is_available():
            return self.speex_aec.process(mic_chunk, ref_chunk)
        elif self.nlms_aec is not None:
            return self.nlms_aec.process(mic_chunk, ref_chunk)
        return mic_chunk

    def destroy(self) -> None:
        self.speex_aec.destroy()

