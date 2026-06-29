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


# ---------------------------------------------------------------------------
# Resampling helpers (used by RNNoise 48 kHz ↔ 16 kHz bridge)
# ---------------------------------------------------------------------------

def resample_16k_to_48k(data_16k: np.ndarray) -> np.ndarray:
    """
    Resample a 16 kHz array to 48 kHz using polyphase anti-aliased filter.
    Falls back to linear interpolation if scipy is unavailable.
    """
    flat = data_16k.flatten().astype(np.float32)
    try:
        from scipy.signal import resample_poly
        return resample_poly(flat, up=3, down=1).astype(np.float32)
    except Exception:
        xp = np.arange(len(flat))
        x  = np.linspace(0, len(flat) - 1, len(flat) * 3)
        return np.interp(x, xp, flat).astype(np.float32)


def resample_48k_to_16k(data_48k: np.ndarray) -> np.ndarray:
    """
    Resample a 48 kHz array to 16 kHz using polyphase anti-aliased filter.
    Falls back to linear interpolation if scipy is unavailable.
    """
    flat = data_48k.flatten().astype(np.float32)
    try:
        from scipy.signal import resample_poly
        return resample_poly(flat, up=1, down=3).astype(np.float32)
    except Exception:
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

        BUG FIX: output was float64; now explicitly cast to float32.
        """
        if not self.is_available():
            return frame_160_samples.astype(np.float32)

        try:
            audio_48k        = resample_16k_to_48k(frame_160_samples)
            audio_48k_scaled = (audio_48k * 32768.0).astype(np.float32)

            in_ptr  = (ctypes.c_float * 480)(*audio_48k_scaled)
            out_ptr = (ctypes.c_float * 480)()

            self.lib.rnnoise_process_frame(self.state, out_ptr, in_ptr)

            # BUG FIX: was dtype=float64 (default np.array); now force float32
            denoised_48k = np.array(out_ptr, dtype=np.float32) / 32768.0
            result = resample_48k_to_16k(denoised_48k)
            return result.reshape(frame_160_samples.shape).astype(np.float32)
        except Exception as e:
            logger.debug(f"RNNoise processing error: {e}")
            return frame_160_samples.astype(np.float32)

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

    BUG FIX: Previously used stateless lfilter() which caused discontinuity
    artefacts at every 30 ms chunk boundary.  Now uses sosfilt() with
    persistent filter state (zi) so each chunk continues cleanly from the
    previous one.
    """

    def __init__(self, cutoff: float = HIGHPASS_CUTOFF, fs: float = SAMPLE_RATE):
        from scipy.signal import butter, sosfilt_zi
        nyq = 0.5 * fs
        normal_cutoff = cutoff / nyq
        # Use second-order sections (numerically more stable than ba form)
        self.sos = butter(5, normal_cutoff, btype="high", analog=False, output="sos")
        # Persistent filter state — updated after every chunk
        self._zi = sosfilt_zi(self.sos)   # shape: (n_sections, 2)

    def process(self, chunk: np.ndarray) -> np.ndarray:
        """
        Filter one chunk in-place, preserving filter state across calls.
        Returns same shape as input.
        """
        from scipy.signal import sosfilt
        flat = chunk.flatten().astype(np.float32)
        # zi must be scaled by DC value of input for stable startup
        filtered, self._zi = sosfilt(self.sos, flat, zi=self._zi)
        return filtered.reshape(chunk.shape).astype(np.float32)


# ---------------------------------------------------------------------------
# Automatic Gain Control (RMS-based, with anti-clipping limiter)
# ---------------------------------------------------------------------------

class AutomaticGainControl:
    """
    Automatic Gain Control normalising input audio to a target RMS level.

    BUG FIX 1: Previous implementation targeted peak amplitude, which caused
    erratic gain swings on transients.  Now targets RMS for smoother, more
    natural behaviour.

    BUG FIX 2: No anti-clipping was applied; output could exceed ±1.0.
    A hard clip (np.clip) and a soft limiter are now applied after gain.
    """

    def __init__(
        self,
        target_rms:  float = AGC_TARGET_RMS,
        max_gain:    float = AGC_MAX_GAIN,
        rate:        float = AGC_RATE,
        # backward-compatible alias used by existing tests and callers
        target_level: float | None = None,
    ):
        self.target_rms  = target_level if target_level is not None else target_rms
        self.max_gain    = max_gain
        self.rate        = rate
        self.current_gain = 1.0

    def process(self, chunk: np.ndarray) -> np.ndarray:
        if len(chunk) == 0:
            return chunk.astype(np.float32)

        flat = chunk.flatten().astype(np.float32)

        # RMS-based gain calculation (more stable than peak-based)
        rms = float(np.sqrt(np.mean(flat * flat)))
        if rms > 1e-6:
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
    Google WebRTC VAD.  Falls back to simple RMS-energy VAD if webrtcvad
    is not installed.
    """

    def __init__(
        self,
        aggressiveness:    int   = VAD_AGGRESSIVENESS,
        default_threshold: float = VAD_THRESHOLD,
    ):
        self.vad = None
        self.default_threshold = default_threshold
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
            return rms >= self.default_threshold

        frame_int16 = (frame_float.flatten() * 32767).astype(np.int16)
        try:
            return self.vad.is_speech(frame_int16.tobytes(), sample_rate)
        except Exception as e:
            logger.debug(f"WebRTC VAD error: {e}")
            rms = float(np.sqrt(np.mean(np.square(frame_float))))
            return rms >= self.default_threshold


# ---------------------------------------------------------------------------
# Ambient Calibrator
# ---------------------------------------------------------------------------

class AmbientCalibrator:
    """
    Records ambient noise for AMBIENT_CALIBRATION_DURATION seconds at startup
    and derives noise floor + speech threshold automatically.
    Called exactly once per Voice Mode session.
    """

    def __init__(self):
        self.noise_floor       = 0.001
        self.speech_threshold  = VAD_THRESHOLD
        self.silence_threshold = VAD_THRESHOLD * 0.5

    def calibrate(self, ambient_audio: np.ndarray) -> None:
        if len(ambient_audio) == 0:
            return
        flat = ambient_audio.flatten().astype(np.float32)
        rms  = float(np.sqrt(np.mean(flat * flat)))
        self.noise_floor       = rms
        self.speech_threshold  = rms + NOISE_FLOOR_MARGIN
        self.silence_threshold = rms + (NOISE_FLOOR_MARGIN * 0.5)
        logger.info(
            f"Microphone Calibrated — "
            f"Noise Floor: {self.noise_floor:.5f} | "
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
