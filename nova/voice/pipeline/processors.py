"""
Consolidated audio pipeline and state machine orchestration for the Nova Voice subsystem.
"""
from __future__ import annotations

import os
import time
import ctypes
import ctypes.util
from typing import Optional
import threading
import collections
import json

import numpy as np

try:
    from scipy.signal import resample_poly, butter, sosfilt, sosfilt_zi, welch, spectrogram
except ImportError:
    resample_poly = None
    butter = None
    sosfilt = None
    sosfilt_zi = None
    welch = None
    spectrogram = None

import nova.voice.config as voice_config
from nova.voice.config import (
    SAMPLE_RATE, VAD_THRESHOLD, NOISE_FLOOR_MARGIN, HIGHPASS_CUTOFF,
    VAD_AGGRESSIVENESS, AGC_TARGET_RMS, AGC_MAX_GAIN, AGC_RATE
)
from nova.logger import logger
from nova.utils import print_warning
from nova.voice.async_log import async_log

def resample_16k_to_48k(data_16k: np.ndarray) -> np.ndarray:
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
    flat = data_48k.flatten().astype(np.float32)
    if resample_poly is not None:
        try:
            return resample_poly(flat, up=1, down=3).astype(np.float32)
        except Exception:
            pass
    xp = np.arange(len(flat))
    x  = np.linspace(0, len(flat) - 1, len(flat) // 3)
    return np.interp(x, xp, flat).astype(np.float32)



class RNNoiseWrapper:
    def __init__(self):
        self.lib   = None
        self.state = None

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
        if len(chunk_480_samples) == 0:
            return chunk_480_samples.astype(np.float32)
        if not self.is_available():
            return chunk_480_samples.astype(np.float32)

        original_shape = chunk_480_samples.shape
        flat_audio = chunk_480_samples.flatten()
        original_len = len(flat_audio)
        
        if original_len % 480 != 0:
            pad_len = 480 - (original_len % 480)
            flat_audio = np.pad(flat_audio, (0, pad_len), mode="constant").astype(np.float32)
        
        try:
            n_blocks = len(flat_audio) // 480
            audio_48k        = resample_16k_to_48k(flat_audio)
            audio_48k_scaled = (audio_48k * 32768.0).astype(np.float32)
            out_array = np.zeros(n_blocks * 1440, dtype=np.float32)

            for i in range(n_blocks * 3):
                offset = i * 480
                in_slice = audio_48k_scaled[offset:offset+480]
                out_slice = out_array[offset:offset+480]
                
                in_ptr_offset  = in_slice.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
                out_ptr_offset = out_slice.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
                self.lib.rnnoise_process_frame(self.state, out_ptr_offset, in_ptr_offset)

            denoised_48k = out_array / 32768.0
            result = resample_48k_to_16k(denoised_48k)
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


class HighPassFilter:
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
                self.sos = butter(5, normal_cutoff, btype="high", analog=False, output="sos")
                self._zi = sosfilt_zi(self.sos)
            except Exception as e:
                logger.warning(f"High-pass filter initialization failed: {e}. Filter will be bypassed.")
        else:
            logger.warning(f"Invalid high-pass cutoff {cutoff} for sample rate {fs}. Filter will be bypassed.")

    def process(self, chunk: np.ndarray) -> np.ndarray:
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


class AutomaticGainControl:
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
        rms = float(np.sqrt(np.mean(flat * flat)))
        if rms > 1e-6:
            if speech_active and (rms > self.noise_floor * 1.5):
                target_gain = min(self.target_rms / rms, self.max_gain)
                self.current_gain += (target_gain - self.current_gain) * self.rate
        amplified = flat * self.current_gain
        output = amplified.copy()
        abs_output = np.abs(output)
        over_mask = abs_output > 0.9
        if np.any(over_mask):
            sgn = np.sign(output[over_mask])
            val = abs_output[over_mask]
            output[over_mask] = sgn * (0.9 + 0.1 * np.tanh((val - 0.9) / 0.1))
        return output.reshape(chunk.shape).astype(np.float32)


class WebRTCVoiceActivityDetector:
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


class AmbientCalibrator:
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
            frame_rms.sort()
            idx = max(0, int(len(frame_rms) * 0.1))
            rms = frame_rms[idx]
        else:
            rms = float(np.sqrt(np.mean(flat * flat)))

        self.noise_floor       = rms
        self.speech_threshold  = rms + NOISE_FLOOR_MARGIN
        self.silence_threshold = rms + (NOISE_FLOOR_MARGIN * 0.5)
        logger.info(
            f"Microphone Calibrated — Noise Floor: {self.noise_floor:.5f} | Speech Threshold: {self.speech_threshold:.5f}"
        )


class AudioDiagnostics:
    CLIPPING_WARN_PCT  = 0.5
    RMS_TOO_QUIET      = 0.002
    NOISE_FLOOR_HIGH   = 0.05
    SNR_WARN_DB        = 10.0

    def __init__(self, sample_rate: int = SAMPLE_RATE, frame_size: int = 480):
        self.sample_rate = sample_rate
        self.frame_size  = frame_size

    def measure(self, audio: np.ndarray) -> dict:
        flat = audio.flatten().astype(np.float32)
        if len(flat) == 0:
            return {}

        rms  = float(np.sqrt(np.mean(flat * flat)))
        peak = float(np.max(np.abs(flat)))
        clipping_count = int(np.sum(np.abs(flat) >= 0.99))
        clipping_pct   = 100.0 * clipping_count / len(flat)

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
            noise_floor = rms * 0.3

        if noise_floor > 1e-9:
            snr_db = 20.0 * np.log10(rms / noise_floor) if rms > noise_floor else 0.0
        else:
            snr_db = float("inf")

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

        if rms < self.RMS_TOO_QUIET:
            print_warning(f"Microphone signal very quiet (RMS={rms:.4f})")
        if clipping_pct > self.CLIPPING_WARN_PCT:
            print_warning(f"Audio clipping detected ({clipping_pct:.1f}% of samples)")
        if noise_floor > self.NOISE_FLOOR_HIGH:
            print_warning(f"High background noise floor ({noise_floor:.4f})")
        if 0 < snr_db < self.SNR_WARN_DB:
            print_warning(f"Low SNR ({snr_db:.1f} dB)")

        return metrics


def select_best_microphone() -> dict | None:
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
            pass

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
    return default


def get_reference_chunk(chunk_size: int = 480) -> np.ndarray | None:
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
    def __init__(self, frame_size: int = 480, filter_len: int = 3200):
        self.lib = None
        self.state = None
        self.frame_size = frame_size

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
        rec_short = (np.clip(rec_flat, -1.0, 1.0) * 32767).astype(np.int16)
        play_short = (np.clip(play_flat, -1.0, 1.0) * 32767).astype(np.int16)
        out_short = np.zeros(self.frame_size, dtype=np.int16)

        try:
            rec_ptr = rec_short.ctypes.data_as(ctypes.POINTER(ctypes.c_short))
            play_ptr = play_short.ctypes.data_as(ctypes.POINTER(ctypes.c_short))
            out_ptr = out_short.ctypes.data_as(ctypes.POINTER(ctypes.c_short))
            self.lib.speex_echo_cancellation(self.state, rec_ptr, play_ptr, out_ptr)
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
        self.x_history[:-self.frame_size] = self.x_history[self.frame_size:]
        self.x_history[-self.frame_size:] = play_flat
        out = np.zeros(self.frame_size, dtype=np.float32)
        for i in range(self.frame_size):
            x_vec = self.x_history[i : i + self.filter_len]
            y_hat = np.dot(self.w, x_vec)
            err = rec_flat[i] - y_hat
            out[i] = err
            norm_x = np.dot(x_vec, x_vec)
            self.w += self.mu * err * x_vec / (norm_x + self.eps)
        return out.reshape(rec.shape)


class AecProcessor:
    def __init__(self, frame_size: int = 480, filter_len: int = 3200):
        self.speex_aec = SpeexEchoCanceller(frame_size, filter_len)
        self.nlms_aec = NLMSEchoCanceller(frame_size, filter_len) if not self.speex_aec.is_available() else None

    def process(self, mic_chunk: np.ndarray) -> np.ndarray:
        from nova.voice.config import ENABLE_ECHO_CANCEL
        if not ENABLE_ECHO_CANCEL:
            return mic_chunk
        ref_chunk = get_reference_chunk(len(mic_chunk))
        if ref_chunk is None:
            return mic_chunk
        if self.speex_aec.is_available():
            return self.speex_aec.process(mic_chunk, ref_chunk)
        elif self.nlms_aec is not None:
            return self.nlms_aec.process(mic_chunk, ref_chunk)
        return mic_chunk

    def destroy(self) -> None:
        self.speex_aec.destroy()


# ---------------------------------------------------------------------------
# Audio Quality Analysis
# ---------------------------------------------------------------------------

class AudioQualityAnalyzer:
    def __init__(self, sample_rate: int = 16000, frame_size: int = 480):
        self.sample_rate = sample_rate
        self.frame_size = frame_size

    def analyze(self, audio: np.ndarray, ref_audio: np.ndarray | None = None) -> dict[str, float]:
        flat = audio.flatten().astype(np.float32)
        if len(flat) == 0:
            return {
                "snr_db": 0.0,
                "background_noise": 0.0,
                "clipping_pct": 0.0,
                "voice_volume": 0.0,
                "echo_level": 0.0,
                "overall_quality": 0.0
            }

        n_frames = len(flat) // self.frame_size
        frame_rms = []
        for i in range(max(1, n_frames)):
            start = i * self.frame_size
            end = min(len(flat), start + self.frame_size)
            frame = flat[start:end]
            if len(frame) > 0:
                frame_rms.append(float(np.sqrt(np.mean(frame * frame))))
        frame_rms.sort()
        n_quietest = max(1, len(frame_rms) // 10)
        background_noise = float(np.mean(frame_rms[:n_quietest]))
        n_loudest = max(1, int(len(frame_rms) * 0.3))
        signal_rms = float(np.mean(frame_rms[-n_loudest:]))
        
        if background_noise > 1e-9:
            snr_db = float(20.0 * np.log10(signal_rms / background_noise))
            if snr_db < 0.0:
                snr_db = 0.0
        else:
            snr_db = 100.0

        clipping_count = int(np.sum(np.abs(flat) >= 0.99))
        clipping_pct = float((clipping_count / len(flat)) * 100.0)

        speech_frames = [r for r in frame_rms if r > background_noise * 1.8]
        if speech_frames:
            voice_volume = float(np.mean(speech_frames))
        else:
            voice_volume = float(np.mean(frame_rms))

        echo_level = 0.0
        if ref_audio is not None and len(ref_audio) > 0:
            ref_flat = ref_audio.flatten().astype(np.float32)
            min_len = min(len(flat), len(ref_flat))
            if min_len > 10:
                s1 = flat[:min_len]
                s2 = ref_flat[:min_len]
                norm1 = np.linalg.norm(s1)
                norm2 = np.linalg.norm(s2)
                if norm1 > 1e-6 and norm2 > 1e-6:
                    corr = np.abs(np.dot(s1, s2)) / (norm1 * norm2)
                    echo_level = float(min(1.0, max(0.0, corr)))

        snr_score = min(1.0, max(0.0, (snr_db - 5.0) / 20.0))
        clipping_penalty = min(1.0, clipping_pct / 1.0)
        noise_penalty = min(1.0, background_noise * 10.0)
        volume_score = 1.0
        if voice_volume < 0.005:
            volume_score = float(max(0.0, voice_volume / 0.005))
        echo_penalty = min(1.0, echo_level * 1.67)

        overall = (snr_score * 0.4 + (1.0 - noise_penalty) * 0.3 + volume_score * 0.3) * (1.0 - clipping_penalty) * (1.0 - echo_penalty)
        overall_quality = float(min(1.0, max(0.0, overall)))

        return {
            "snr_db": snr_db,
            "background_noise": background_noise,
            "clipping_pct": clipping_pct,
            "voice_volume": voice_volume,
            "echo_level": echo_level,
            "overall_quality": overall_quality
        }


# ---------------------------------------------------------------------------
# Confidence Fusion Engine
# ---------------------------------------------------------------------------

class ConfidenceFusionEngine:
    def __init__(self, weights: dict[str, float] = None) -> None:
        self.weights = weights or {
            "wake": getattr(voice_config, "FUSION_WEIGHT_WAKE", 0.40),
            "speaker": getattr(voice_config, "FUSION_WEIGHT_SPEAKER", 0.30),
            "vad": getattr(voice_config, "FUSION_WEIGHT_VAD", 0.15),
            "quality": getattr(voice_config, "FUSION_WEIGHT_QUALITY", 0.10),
            "noise": getattr(voice_config, "FUSION_WEIGHT_NOISE", 0.05)
        }
        self._custom_sources = []
        self.diagnostics_path = os.path.expanduser("~/.config/nova/fusion_logs.json")
        self.history = []

    def register_source(self, name: str, weight: float, scorer_callable: callable) -> None:
        self._custom_sources = [s for s in self._custom_sources if s[0] != name]
        self._custom_sources.append((name, weight, scorer_callable))
        self.weights[name] = weight
        logger.info(f"Registered custom confidence source '{name}' with weight {weight:.3f}")

    def fuse(
        self,
        wake_score: float,
        speaker_score: float | None = None,
        vad_score: float | None = None,
        audio_quality: float | None = None,
        noise_level: float | None = None,
        **kwargs
    ) -> float:
        raw_inputs = {
            "wake": wake_score,
            "speaker": speaker_score,
            "vad": vad_score,
            "quality": audio_quality,
        }
        if noise_level is not None:
            raw_inputs["noise"] = max(0.0, 1.0 - (noise_level * 10.0))
        else:
            raw_inputs["noise"] = None

        for name, _, scorer_callable in self._custom_sources:
            try:
                score = scorer_callable(**kwargs)
                raw_inputs[name] = float(score) if score is not None else None
            except Exception as e:
                logger.debug(f"Custom confidence source '{name}' failed: {e}")
                raw_inputs[name] = None

        active_scores = {}
        for name, score in raw_inputs.items():
            if score is not None:
                active_scores[name] = min(1.0, max(0.0, float(score)))

        if not active_scores:
            return 0.0

        active_weights = {}
        total_weight = 0.0
        for name in active_scores:
            w = self.weights.get(name, 0.0)
            active_weights[name] = w
            total_weight += w

        if total_weight < 1e-9:
            equal_w = 1.0 / len(active_scores)
            active_weights = {name: equal_w for name in active_scores}
            total_weight = 1.0

        fused_score = 0.0
        for name, score in active_scores.items():
            normalized_weight = active_weights[name] / total_weight
            fused_score += score * normalized_weight

        self._log_diagnostics(active_scores, active_weights, total_weight, fused_score)
        return min(1.0, max(0.0, float(fused_score)))

    def _log_diagnostics(self, scores: dict, weights: dict, total_weight: float, fused: float) -> None:
        diag = {
            "timestamp": time.time(),
            "event": "confidence_fusion",
            "scores": {k: float(v) for k, v in scores.items()},
            "weights": {k: float(v / total_weight) for k, v in weights.items()},
            "fused_score": float(fused)
        }
        self.history.append(diag)
        self.history = self.history[-500:]
        async_log(self.diagnostics_path, diag, 500)


# ---------------------------------------------------------------------------
# Diagnostics Engine
# ---------------------------------------------------------------------------

def _pct(value: float, digits: int = 2) -> str:
    return f"{value * 100:.{digits}f}%"


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _safe_mean(seq) -> float:
    lst = list(seq)
    return sum(lst) / len(lst) if lst else 0.0


def _safe_min(seq) -> float:
    lst = list(seq)
    return min(lst) if lst else 0.0


def _safe_max(seq) -> float:
    lst = list(seq)
    return max(lst) if lst else 0.0


_MAX_HISTORY = 500


class VoiceDiagnosticsEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wake_successes: collections.deque[dict] = collections.deque(maxlen=_MAX_HISTORY)
        self._false_wakes:    collections.deque[dict] = collections.deque(maxlen=_MAX_HISTORY)
        self._missed_wakes:   collections.deque[dict] = collections.deque(maxlen=_MAX_HISTORY)
        self._turns: collections.deque[dict] = collections.deque(maxlen=_MAX_HISTORY)
        self._quality_snapshots: collections.deque[dict] = collections.deque(maxlen=_MAX_HISTORY)
        self._noise_history: collections.deque[float] = collections.deque(maxlen=_MAX_HISTORY)
        self._speaker_confidence: collections.deque[float] = collections.deque(maxlen=_MAX_HISTORY)
        self._diag_path = os.path.expanduser("~/.config/nova/voice_diagnostics.json")
        os.makedirs(os.path.dirname(self._diag_path), exist_ok=True)
        self._session_start = time.time()

    def record_wake_success(self, score: float, latency_ms: float) -> None:
        with self._lock:
            self._wake_successes.append({
                "ts": time.time(),
                "score": float(score),
                "latency_ms": float(latency_ms),
            })

    def record_false_wake(self, score: float, noise_floor: float) -> None:
        with self._lock:
            self._false_wakes.append({
                "ts": time.time(),
                "score": float(score),
                "noise_floor": float(noise_floor),
            })

    def record_missed_wake(self, score: float, noise_floor: float) -> None:
        with self._lock:
            self._missed_wakes.append({
                "ts": time.time(),
                "score": float(score),
                "noise_floor": float(noise_floor),
            })

    def record_turn(
        self,
        latency_ms: float,
        stt_latency_ms: float = 0.0,
        tts_latency_ms: float = 0.0,
        audio_quality: float = 1.0,
        speaker_confidence: Optional[float] = None,
        noise_floor: float = 0.0,
    ) -> None:
        with self._lock:
            self._turns.append({
                "ts": time.time(),
                "latency_ms": float(latency_ms),
                "stt_latency_ms": float(stt_latency_ms),
                "tts_latency_ms": float(tts_latency_ms),
                "audio_quality": float(audio_quality),
                "noise_floor": float(noise_floor),
            })
            if speaker_confidence is not None:
                self._speaker_confidence.append(float(speaker_confidence))

    def record_audio_quality(self, metrics: dict) -> None:
        with self._lock:
            self._quality_snapshots.append({
                "ts": time.time(),
                **{k: float(v) for k, v in metrics.items()},
            })

    def record_noise_sample(self, rms: float) -> None:
        with self._lock:
            self._noise_history.append(float(rms))

    def get_wake_stats(self) -> dict:
        with self._lock:
            n_success = len(self._wake_successes)
            n_false   = len(self._false_wakes)
            n_missed  = len(self._missed_wakes)
            total     = n_success + n_false
            rate      = (n_success / total) if total > 0 else 0.0
            latencies = [e["latency_ms"] for e in self._wake_successes]
            scores    = [e["score"]      for e in self._wake_successes]
        return {
            "success_count":   n_success,
            "false_wake_count": n_false,
            "missed_wake_count": n_missed,
            "total_triggers":  total,
            "success_rate":    round(rate, 4),
            "avg_wake_latency_ms": round(_safe_mean(latencies), 2),
            "avg_wake_score":  round(_safe_mean(scores), 4),
        }

    def get_latency_stats(self) -> dict:
        with self._lock:
            e2e  = [t["latency_ms"]     for t in self._turns]
            stt  = [t["stt_latency_ms"] for t in self._turns]
            tts  = [t["tts_latency_ms"] for t in self._turns]

        def _stats(data: list[float], label: str) -> dict:
            return {
                f"{label}_avg_ms":  round(_safe_mean(data), 2),
                f"{label}_min_ms":  round(_safe_min(data), 2),
                f"{label}_max_ms":  round(_safe_max(data), 2),
                f"{label}_p95_ms":  round(_percentile(data, 95), 2),
            }

        result = {"turn_count": len(e2e)}
        result.update(_stats(e2e, "e2e"))
        result.update(_stats(stt, "stt"))
        result.update(_stats(tts, "tts"))
        return result

    def get_audio_quality_stats(self) -> dict:
        with self._lock:
            snaps = list(self._quality_snapshots)
        if not snaps:
            return {
                "snapshot_count": 0,
                "avg_snr_db": 0.0,
                "avg_background_noise": 0.0,
                "avg_clipping_pct": 0.0,
                "avg_voice_volume": 0.0,
                "avg_echo_level": 0.0,
                "avg_overall_quality": 0.0,
            }
        keys = ["snr_db", "background_noise", "clipping_pct",
                "voice_volume", "echo_level", "overall_quality"]
        out = {"snapshot_count": len(snaps)}
        for k in keys:
            vals = [s[k] for s in snaps if k in s]
            out[f"avg_{k}"] = round(_safe_mean(vals), 4)
        return out

    def get_noise_history(self, n: int = 50) -> list[float]:
        with self._lock:
            history = list(self._noise_history)
        return history[-n:]

    def get_speaker_confidence_stats(self) -> dict:
        with self._lock:
            conf = list(self._speaker_confidence)
        if not conf:
            return {"sample_count": 0, "avg": 0.0, "min": 0.0, "max": 0.0, "p95": 0.0}
        return {
            "sample_count": len(conf),
            "avg":  round(_safe_mean(conf), 4),
            "min":  round(_safe_min(conf), 4),
            "max":  round(_safe_max(conf), 4),
            "p95":  round(_percentile(conf, 95), 4),
        }

    def get_resource_usage(self) -> dict:
        try:
            import psutil
            proc = psutil.Process(os.getpid())
            return {
                "cpu_pct":      round(proc.cpu_percent(interval=0.1), 1),
                "memory_mb":    round(proc.memory_info().rss / 1_048_576, 1),
                "thread_count": proc.num_threads(),
            }
        except ImportError:
            try:
                import resource as _res
                usage = _res.getrusage(_res.RUSAGE_SELF)
                kb = usage.ru_maxrss
                return {
                    "cpu_pct": None,
                    "memory_mb": round(kb / 1024.0, 1),
                    "thread_count": None,
                }
            except Exception:
                return {"cpu_pct": None, "memory_mb": None, "thread_count": None}
        except Exception as e:
            logger.debug(f"Resource usage query failed: {e}")
            return {"cpu_pct": None, "memory_mb": None, "thread_count": None}

    def generate_report(self, fmt: str = "text") -> str:
        wake    = self.get_wake_stats()
        latency = self.get_latency_stats()
        quality = self.get_audio_quality_stats()
        speaker = self.get_speaker_confidence_stats()
        noise   = self.get_noise_history(n=50)
        res     = self.get_resource_usage()
        uptime_s = time.time() - self._session_start

        if fmt == "json":
            report = {
                "generated_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "session_uptime_s": round(uptime_s, 1),
                "wake":           wake,
                "latency":        latency,
                "audio_quality":  quality,
                "speaker":        speaker,
                "noise_history":  [round(v, 5) for v in noise],
                "resource_usage": res,
            }
            return json.dumps(report, indent=2)

        lines = [
            "╔══════════════════════════════════════════════════════╗",
            "║         Nova Voice Diagnostics Report                ║",
            "╚══════════════════════════════════════════════════════╝",
            f"  Generated : {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"  Uptime    : {int(uptime_s // 60)}m {int(uptime_s % 60)}s",
            "",
            "── Wake-Word ─────────────────────────────────────────",
            f"  Successes     : {wake['success_count']}",
            f"  False wakes   : {wake['false_wake_count']}",
            f"  Missed wakes  : {wake['missed_wake_count']}",
            f"  Success rate  : {_pct(wake['success_rate'])}",
            f"  Avg score     : {wake['avg_wake_score']:.4f}",
            f"  Avg latency   : {wake['avg_wake_latency_ms']:.1f} ms",
            "",
            "── Latency ───────────────────────────────────────────",
            f"  Turns logged  : {latency['turn_count']}",
            f"  E2E avg/p95   : {latency['e2e_avg_ms']:.0f} ms / {latency['e2e_p95_ms']:.0f} ms",
            f"  STT avg/p95   : {latency['stt_avg_ms']:.0f} ms / {latency['stt_p95_ms']:.0f} ms",
            f"  TTS avg/p95   : {latency['tts_avg_ms']:.0f} ms / {latency['tts_p95_ms']:.0f} ms",
            "",
            "── Audio Quality ─────────────────────────────────────",
            f"  Snapshots     : {quality['snapshot_count']}",
            f"  Avg SNR       : {quality['avg_snr_db']:.1f} dB",
            f"  Avg noise RMS : {quality['avg_background_noise']:.5f}",
            f"  Avg clipping  : {quality['avg_clipping_pct']:.2f}%",
            f"  Avg echo lvl  : {quality['avg_echo_level']:.4f}",
            f"  Avg quality   : {quality['avg_overall_quality']:.3f} / 1.000",
            "",
            "── Speaker Confidence ────────────────────────────────",
            f"  Samples       : {speaker['sample_count']}",
            f"  Avg / p95     : {speaker['avg']:.4f} / {speaker['p95']:.4f}",
            f"  Min / Max     : {speaker['min']:.4f} / {speaker['max']:.4f}",
            "",
            "── Ambient Noise (last 10 samples) ───────────────────",
        ]
        noise_tail = noise[-10:]
        if noise_tail:
            bar_line = "  " + "  ".join(f"{v:.4f}" for v in noise_tail)
            lines.append(bar_line)
        else:
            lines.append("  (no samples yet)")
        lines.append("")
        lines += [
            "── Resource Usage ────────────────────────────────────",
            f"  CPU           : {res['cpu_pct']}%",
            f"  Memory (RSS)  : {res['memory_mb']} MB",
            f"  Threads       : {res['thread_count']}",
            "",
            "══════════════════════════════════════════════════════",
        ]
        return "\n".join(lines)

    def save_report(self, path: Optional[str] = None) -> str:
        if path is None:
            path = os.path.expanduser("~/.config/nova/diagnostics_report.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        report = self.generate_report(fmt="text")
        with open(path, "w") as f:
            f.write(report)
        logger.info(f"Diagnostics report saved: {path}")
        return path

    def flush_to_disk(self) -> None:
        try:
            payload = {
                "flushed_at": time.time(),
                "wake":    self.get_wake_stats(),
                "latency": self.get_latency_stats(),
                "quality": self.get_audio_quality_stats(),
                "speaker": self.get_speaker_confidence_stats(),
            }
            with open(self._diag_path, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.debug(f"Diagnostics flush failed: {e}")



