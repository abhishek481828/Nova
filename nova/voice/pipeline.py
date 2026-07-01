"""
Consolidated audio pipeline and state machine orchestration for the Nova Voice subsystem.
"""
from __future__ import annotations

import os
import re
import time
import json
import queue
import atexit
import ctypes
import ctypes.util
import threading
import collections
import random
import subprocess
import wave
import io
from enum import Enum, auto
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import numpy as np
import sounddevice as sd

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
    SAMPLE_RATE, CHANNELS, RECORDING_TIMEOUT, SILENCE_TIMEOUT, TEMP_AUDIO_DIR,
    VAD_THRESHOLD, NOISE_FLOOR_MARGIN, HIGHPASS_CUTOFF, VAD_AGGRESSIVENESS,
    ENABLE_NOISE_SUPPRESSION, ENABLE_HIGHPASS_FILTER, ENABLE_AGC, ENABLE_VAD,
    ENABLE_DC_OFFSET_REMOVAL, BLOCK_SIZE,
    VAD_PRE_PADDING_FRAMES, VAD_POST_PADDING_FRAMES, enable_debug,
    enable_wake_word, wake_word_phrase, wake_word_model_path,
    wake_word_threshold, confirmation_sound, enable_speaker_verification,
    speaker_similarity_threshold, speaker_embedding_path,
    AGC_TARGET_RMS, AGC_MAX_GAIN, AGC_RATE, AMBIENT_CALIBRATION_DURATION,
)
from nova.logger import logger
from nova.utils import (
    print_info, print_warning, print_error, print_success,
    COLOR_BOLD, COLOR_RESET, COLOR_CYAN, COLOR_RED
)

from nova.voice.speaker import SpeakerVerifier
from nova.voice.whisper import get_stt_provider
from nova.voice.tts import speak
from nova.voice.wakeword import LocalWakeWordDetector, AdaptiveWakeController


# ---------------------------------------------------------------------------
# Asynchronous Logging Service
# ---------------------------------------------------------------------------

class AsyncLogger:
    def __init__(self, flush_interval_secs: float = 1.0) -> None:
        self._queue: queue.Queue[Tuple[str, dict, int]] = queue.Queue()
        self._buffers: Dict[str, List[dict]] = {}
        self._max_lens: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._disk_lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._flush_interval = flush_interval_secs
        self._stop_event = threading.Event()
        
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="nova_async_logging_worker"
        )
        self._worker_thread.start()
        atexit.register(self.shutdown)

    def log(self, file_path: str, entry: dict, max_entries: int = 500) -> None:
        norm_path = os.path.abspath(os.path.expanduser(file_path))
        logger.debug(f"[AsyncLogger.log] Enqueuing log event: {entry.get('event')} to {norm_path}")
        self._queue.put((norm_path, entry, max_entries))

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=self._flush_interval)
                self._buffer_item(item)
                
                while not self._queue.empty():
                    item = self._queue.get_nowait()
                    self._buffer_item(item)
                    self._queue.task_done()
                    
                self._queue.task_done()
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Error in async logging worker: {e}")
                
            self.flush()

    def _buffer_item(self, item: Tuple[str, dict, int]) -> None:
        file_path, entry, max_entries = item
        with self._lock:
            if file_path not in self._buffers:
                self._buffers[file_path] = []
            self._buffers[file_path].append(entry)
            self._max_lens[file_path] = max_entries

    def flush(self) -> None:
        if not hasattr(self, '_flush_lock'):
            self._flush_lock = threading.Lock()
        with self._flush_lock:
            while not self._queue.empty():
                try:
                    item = self._queue.get_nowait()
                    self._buffer_item(item)
                    self._queue.task_done()
                except queue.Empty:
                    break

            with self._lock:
                if not self._buffers:
                    return
                buffers_to_flush = dict(self._buffers)
                self._buffers.clear()
                max_lens = dict(self._max_lens)
                
            for file_path, new_entries in buffers_to_flush.items():
                max_len = max_lens.get(file_path, 500)
                self._write_to_disk(file_path, new_entries, max_len)

    def _write_to_disk(self, file_path: str, new_entries: List[dict], max_len: int) -> None:
        if not hasattr(self, '_disk_lock'):
            self._disk_lock = threading.Lock()
        with self._disk_lock:
            logs = []
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r") as f:
                        logs = json.load(f)
                        if not isinstance(logs, list):
                            logs = []
                except Exception as e:
                    logger.debug(f"[_write_to_disk] Error reading existing file: {e}")
                    logs = []
                    
            logs.extend(new_entries)
            logs = logs[-max_len:]
            
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                temp_path = file_path + ".tmp"
                with open(temp_path, "w") as f:
                    json.dump(logs, f, indent=2)
                os.replace(temp_path, file_path)
            except Exception as e:
                logger.debug(f"Failed async write to {file_path}: {e}")

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                self._buffer_item(item)
                self._queue.task_done()
            except queue.Empty:
                break
        self.flush()
        try:
            self._worker_thread.join(timeout=1.0)
        except Exception:
            pass

_async_logger = AsyncLogger()

def async_log(file_path: str, entry: dict, max_entries: int = 500) -> None:
    _async_logger.log(file_path, entry, max_entries)


# ---------------------------------------------------------------------------
# Audio Processing Utilities
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Dynamic Greetings Builder
# ---------------------------------------------------------------------------

_recent_greetings: collections.deque[str] = collections.deque(maxlen=5)

def _get_user_name() -> str:
    try:
        from nova.core.state import StateManager
        StateManager.load_state()
        profile = StateManager.get_user_profile()
        if profile and isinstance(profile, dict) and profile.get("name"):
            name = profile["name"]
            return name.split()[0] if " " in name else name
    except Exception:
        pass
    return "Boss"


_MORNING_GREETINGS = [
    "Good morning, {name}. I hope you're having a great start to your day.",
    "Good morning, {name}. I'm ready whenever you need me.",
    "Morning, {name}. What would you like to work on today?",
    "Good morning, {name}. Everything is ready whenever you are.",
    "Good morning, {name}. Let me know how I can help today.",
    "Morning, {name}. I hope you slept well. I'm all set.",
    "Good morning, {name}. Ready to get started whenever you are.",
    "Hello, {name}. Good morning. What can I do for you today?",
    "Morning, {name}. It's good to have you back. How can I help?",
    "Good morning, {name}. Just let me know what you'd like to do.",
]

_AFTERNOON_GREETINGS = [
    "Good afternoon, {name}. It's great to have you back.",
    "Welcome back, {name}. How can I help you today?",
    "Good afternoon, {name}. What would you like to work on?",
    "Hello, {name}. I'm ready for your next task.",
    "Good afternoon, {name}. Everything is ready whenever you are.",
    "Welcome back, {name}. What would you like to accomplish today?",
    "Afternoon, {name}. I'm here and ready whenever you need me.",
    "Hello, {name}. Good to see you again. How can I help?",
    "Good afternoon, {name}. Just let me know what you'd like to do.",
    "Welcome back, {name}. I'm all set whenever you're ready.",
]

_EVENING_GREETINGS = [
    "Good evening, {name}. I hope your day has been going well.",
    "Welcome back, {name}. What can I help you with this evening?",
    "Good evening, {name}. I'm ready whenever you are.",
    "Hello again, {name}. What would you like to do tonight?",
    "Good evening, {name}. It's great to have you back.",
    "Evening, {name}. I'm here and ready whenever you need me.",
    "Welcome back, {name}. Let's get started whenever you're ready.",
    "Good evening, {name}. What would you like to work on tonight?",
    "Hello, {name}. I hope your evening is going well. How can I help?",
    "Good evening, {name}. Just let me know what you need.",
]

_NIGHT_GREETINGS = [
    "Good evening, {name}. Working late today? I'm here whenever you need me.",
    "Welcome back, {name}. Let's get started whenever you're ready.",
    "Hello, {name}. What can I help you finish tonight?",
    "Good evening, {name}. I'm ready whenever you are.",
    "Hello, {name}. Burning the midnight oil? I'm right here with you.",
    "Welcome back, {name}. I'm all set whenever you need me.",
    "Good evening, {name}. Let me know what you'd like to work on.",
    "Hello again, {name}. I'm here to help whenever you're ready.",
    "Evening, {name}. I hope you're doing well. What can I help with?",
    "Welcome back, {name}. Just let me know how I can help tonight.",
]

_ADDRESS_FORMS = ["name", "Boss", "Sir"]

def get_activation_greeting() -> str:
    user_name = _get_user_name()
    hour = datetime.now().hour

    if 5 <= hour < 12:
        pool = _MORNING_GREETINGS
    elif 12 <= hour < 17:
        pool = _AFTERNOON_GREETINGS
    elif 17 <= hour < 22:
        pool = _EVENING_GREETINGS
    else:
        pool = _NIGHT_GREETINGS

    address = random.choice(_ADDRESS_FORMS)
    if address == "name":
        address = user_name

    candidates = [g.format(name=address) for g in pool]
    available = [g for g in candidates if g not in _recent_greetings]
    if not available:
        available = candidates

    greeting = random.choice(available)
    _recent_greetings.append(greeting)
    return greeting


# ---------------------------------------------------------------------------
# Audio Recording Routines
# ---------------------------------------------------------------------------

def calculate_rms(audio_chunk: np.ndarray) -> float:
    if len(audio_chunk) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio_chunk))))


def record_audio(output_file: str | None = None, calibrated_threshold: float | None = None) -> bytes | str:
    try:
        import sounddevice as sd
    except ImportError as e:
        logger.debug(f"Failed to import sounddevice: {e}")
        raise RuntimeError("Microphone or audio system not available.")

    print_info("🎤 Listening...")
    rms_threshold = calibrated_threshold if calibrated_threshold is not None else VAD_THRESHOLD
    
    from nova.voice.config import ENABLE_ECHO_CANCEL
    aec = AecProcessor() if ENABLE_ECHO_CANCEL else None
    hp_filter = HighPassFilter(cutoff=HIGHPASS_CUTOFF, fs=SAMPLE_RATE) if ENABLE_HIGHPASS_FILTER else None
    rnnoise = RNNoiseWrapper() if ENABLE_NOISE_SUPPRESSION else None
    agc = AutomaticGainControl() if ENABLE_AGC else None
    vad = WebRTCVoiceActivityDetector(aggressiveness=VAD_AGGRESSIVENESS, default_threshold=rms_threshold) if ENABLE_VAD else None

    if rnnoise and not rnnoise.is_available() and ENABLE_NOISE_SUPPRESSION:
        print_warning("🧹 RNNoise native library not available. Continuing with filters and VAD only.")

    block_samples = BLOCK_SIZE
    audio_data = []
    start_time = time.time()
    last_sound_time = time.time()
    has_speech_started = False
    
    def callback(indata, frames, callback_time, status):
        if status:
            logger.debug(f"Sounddevice status warning: {status}")
        chunk = indata.copy().flatten()
        if ENABLE_DC_OFFSET_REMOVAL:
            chunk = chunk - chunk.mean()
        if aec:
            chunk = aec.process(chunk)
        if agc:
            chunk = agc.process(chunk)
        if hp_filter:
            chunk = hp_filter.process(chunk)
        if rnnoise and rnnoise.is_available():
            chunk = rnnoise.denoise_chunk(chunk)
        chunk = chunk.reshape(-1, 1)
        is_speech = True
        if vad:
            is_speech = vad.is_speech(chunk, SAMPLE_RATE)
        audio_data.append((chunk, is_speech))

    try:
        consecutive_silent_frames = 0
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, callback=callback, blocksize=block_samples):
            while True:
                elapsed = time.time() - start_time
                if elapsed >= RECORDING_TIMEOUT:
                    logger.debug(f"Recording reached maximum timeout of {RECORDING_TIMEOUT} seconds.")
                    break
                
                if len(audio_data) > 0:
                    last_is_speech = audio_data[-1][1]
                    if last_is_speech:
                        last_sound_time = time.time()
                        has_speech_started = True
                        consecutive_silent_frames = 0
                    else:
                        if has_speech_started:
                            consecutive_silent_frames += 1
                            
                    max_silent_frames = int(0.8 / (block_samples / SAMPLE_RATE))
                    silence_duration = time.time() - last_sound_time
                    
                    if has_speech_started and (consecutive_silent_frames >= max_silent_frames or silence_duration >= SILENCE_TIMEOUT):
                        if enable_debug:
                            print_info("🛑 Silence detected (fast endpoint)")
                        break
                    elif not has_speech_started and silence_duration >= 5.0:
                        logger.debug("No speech detected at the start. Stopping.")
                        break
                time.sleep(0.05)
    except Exception as e:
        raise RuntimeError(f"Microphone error: {e}")
    finally:
        if rnnoise:
            rnnoise.destroy()

    first_speech_idx = None
    last_speech_idx = None
    for idx, (_, is_speech) in enumerate(audio_data):
        if is_speech:
            if first_speech_idx is None:
                first_speech_idx = idx
            last_speech_idx = idx
            
    if first_speech_idx is not None and last_speech_idx is not None:
        start_idx = max(0, first_speech_idx - VAD_PRE_PADDING_FRAMES)
        end_idx = min(len(audio_data), last_speech_idx + VAD_POST_PADDING_FRAMES)
        filtered_chunks = [audio_data[i][0] for i in range(start_idx, end_idx)]
    else:
        filtered_chunks = [item[0] for item in audio_data]

    if filtered_chunks:
        recording = np.concatenate(filtered_chunks, axis=0)
    else:
        recording = np.zeros((0, CHANNELS))

    audio_int16 = (recording * 32767).astype(np.int16)
    wav_io = io.BytesIO()
    try:
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())
        wav_bytes = wav_io.getvalue()
    except Exception as e:
        raise RuntimeError(f"Failed to format in-memory WAV data: {e}")

    if output_file is not None:
        try:
            with open(output_file, "wb") as f:
                f.write(wav_bytes)
            return output_file
        except Exception as e:
            raise RuntimeError(f"Failed to write physical WAV file: {e}")
    return wav_bytes


def record_audio_from_stream(
    stream, 
    output_file: str | None = None, 
    calibrated_threshold: float | None = None,
    hp_filter=None,
    rnnoise=None,
    agc=None,
    vad=None,
    aec=None
) -> bytes | str:
    try:
        from nova.dashboard.event_bus import emit
        emit("mic_active", module="voice", status="success", metadata={"samplerate": SAMPLE_RATE, "channels": CHANNELS})
    except Exception:
        pass

    rms_threshold = calibrated_threshold if calibrated_threshold is not None else VAD_THRESHOLD
    from nova.voice.config import ENABLE_ECHO_CANCEL

    local_aec = False
    if aec is None and ENABLE_ECHO_CANCEL:
        aec = AecProcessor()
        local_aec = True

    local_rnnoise = False
    if hp_filter is None:
        hp_filter = HighPassFilter(cutoff=HIGHPASS_CUTOFF, fs=SAMPLE_RATE) if ENABLE_HIGHPASS_FILTER else None
    if rnnoise is None:
        rnnoise = RNNoiseWrapper() if ENABLE_NOISE_SUPPRESSION else None
        local_rnnoise = True
    if agc is None:
        agc = AutomaticGainControl() if ENABLE_AGC else None
    if vad is None:
        vad = WebRTCVoiceActivityDetector(aggressiveness=VAD_AGGRESSIVENESS, default_threshold=rms_threshold) if ENABLE_VAD else None

    if rnnoise and rnnoise.is_available():
        try:
            from nova.dashboard.event_bus import emit
            emit("denoising_start", module="voice", status="success", metadata={"library": "librnnoise"})
        except Exception:
            pass

    if rnnoise and not rnnoise.is_available() and ENABLE_NOISE_SUPPRESSION:
        print_warning("🧹 RNNoise native library not available. Continuing with filters and VAD only.")

    block_samples = BLOCK_SIZE
    audio_data = []
    start_time = time.time()
    last_sound_time = time.time()
    has_speech_started = False
    consecutive_silent_frames = 0
    
    try:
        with voice_config.stream_lock:
            if stream.read_available > 0:
                stream.read(stream.read_available)
            
        while True:
            try:
                if shutdown_event.is_set():
                    break
                if get_current_state() == VoiceState.INACTIVE:
                    logger.debug("Recording interrupted: voice deactivated by user.")
                    break
            except Exception:
                pass
                
            elapsed = time.time() - start_time
            if elapsed >= RECORDING_TIMEOUT:
                logger.debug(f"Recording reached maximum timeout of {RECORDING_TIMEOUT} seconds.")
                break
                
            try:
                with voice_config.stream_lock:
                    indata, overflow = stream.read(block_samples)
            except Exception as e:
                logger.debug(f"Audio stream read error during record: {e}")
                break
                
            chunk = indata.copy().flatten()
            if ENABLE_DC_OFFSET_REMOVAL:
                chunk = chunk - chunk.mean()
            if aec:
                chunk = aec.process(chunk)
            if agc:
                chunk = agc.process(chunk)
            if hp_filter:
                chunk = hp_filter.process(chunk)
            if rnnoise and rnnoise.is_available():
                chunk = rnnoise.denoise_chunk(chunk)
            chunk = chunk.reshape(-1, 1)
            is_speech = True
            if vad:
                is_speech = vad.is_speech(chunk, SAMPLE_RATE)
            audio_data.append((chunk, is_speech))

            if is_speech:
                last_sound_time = time.time()
                consecutive_silent_frames = 0
                if not has_speech_started:
                    try:
                        from nova.dashboard.event_bus import emit
                        emit("speech_detected", module="voice", status="success")
                    except Exception:
                        pass
                has_speech_started = True
            else:
                if has_speech_started:
                    consecutive_silent_frames += 1

            max_silent_frames = int(0.8 / (block_samples / SAMPLE_RATE))
            silence_duration = time.time() - last_sound_time
            
            if has_speech_started and (consecutive_silent_frames >= max_silent_frames or silence_duration >= SILENCE_TIMEOUT):
                if enable_debug:
                    print_info("🛑 Silence detected (fast endpoint)")
                break
            elif not has_speech_started and silence_duration >= 8.0:
                logger.debug("No speech detected within 8 seconds. Stopping.")
                break
                    
    except Exception as e:
        raise RuntimeError(f"Microphone read error: {e}")
    finally:
        if local_rnnoise and rnnoise:
            rnnoise.destroy()
        if local_aec and aec:
            aec.destroy()

    first_speech_idx = None
    last_speech_idx = None
    for idx, (_, is_speech) in enumerate(audio_data):
        if is_speech:
            if first_speech_idx is None:
                first_speech_idx = idx
            last_speech_idx = idx
            
    if first_speech_idx is not None and last_speech_idx is not None:
        start_idx = max(0, first_speech_idx - VAD_PRE_PADDING_FRAMES)
        end_idx = min(len(audio_data), last_speech_idx + VAD_POST_PADDING_FRAMES)
        filtered_chunks = [audio_data[i][0] for i in range(start_idx, end_idx)]
    else:
        filtered_chunks = [item[0] for item in audio_data]

    if filtered_chunks:
        recording = np.concatenate(filtered_chunks, axis=0)
    else:
        recording = np.zeros((0, CHANNELS))

    audio_int16 = (recording * 32767).astype(np.int16)
    wav_io = io.BytesIO()
    try:
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())
        wav_bytes = wav_io.getvalue()
    except Exception as e:
        raise RuntimeError(f"Failed to format in-memory WAV data: {e}")

    try:
        from nova.dashboard.event_bus import emit
        emit("mic_inactive", module="voice", status="success")
    except Exception:
        pass

    if output_file is not None:
        try:
            with open(output_file, "wb") as f:
                f.write(wav_bytes)
            return output_file
        except Exception as e:
            raise RuntimeError(f"Failed to write physical WAV file: {e}")
    return wav_bytes


# ---------------------------------------------------------------------------
# State Machine & Conversation Loop
# ---------------------------------------------------------------------------

class VoiceState(Enum):
    TEXT_MODE = auto()
    VOICE_IDLE = auto()
    WAKE_DETECTED = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    EXECUTING = auto()
    SPEAKING = auto()
    PUSH_TO_TALK = auto()
    SHUTDOWN = auto()
    INACTIVE = auto()


voice_active_event = threading.Event()
shutdown_event = threading.Event()
_current_state = VoiceState.INACTIVE

_mic_healthy = False
_wake_healthy = False
_stt_healthy = False
_deferred_deactivate = False
_state_lock = threading.Lock()

def set_deferred_deactivate(val: bool) -> None:
    global _deferred_deactivate
    _deferred_deactivate = val

def transition_state(new_state: VoiceState) -> None:
    global _current_state
    with _state_lock:
        _current_state = new_state
    logger.debug(f"[STATE] Transitioned to {new_state.name}")

def get_current_state() -> VoiceState:
    global _current_state
    with _state_lock:
        return _current_state

def get_voice_status_report() -> dict:
    from nova.browser.manager import BrowserManager
    from nova.voice.config import ENABLE_TTS
    
    with _state_lock:
        state_name = _current_state.name if _current_state else "UNKNOWN"
    browser_running = BrowserManager.is_browser_running()
    browser_status = "Healthy (Active)" if browser_running else "Inactive"
    
    mic_status = "Healthy (Open)" if _mic_healthy else "Unavailable"
    wake_status = "Healthy (Ready)" if _wake_healthy else "Unavailable"
    stt_status = "Healthy (Ready)" if _stt_healthy else "Unavailable"
    tts_status = "Healthy (Ready)" if ENABLE_TTS else "Disabled"
    health = "Healthy" if (_mic_healthy and _wake_healthy) else "Degraded"
    
    return {
        "running": True,
        "state": state_name,
        "wake_word": wake_status,
        "whisper": stt_status,
        "elevenlabs": tts_status,
        "browser": browser_status,
        "microphone": mic_status,
        "health": health
    }

def recover_microphone(old_stream):
    logger.warning("Microphone error or disconnect detected. Attempting to recover...")
    global _mic_healthy
    _mic_healthy = False
    if old_stream is not None:
        try:
            old_stream.stop()
            old_stream.close()
        except Exception:
            pass
    while not shutdown_event.is_set():
        try:
            if not sd.query_devices(kind="input"):
                raise RuntimeError("No input device available.")
            new_stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32")
            new_stream.start()
            logger.info("Microphone successfully recovered.")
            _mic_healthy = True
            voice_config.active_stream = new_stream
            return new_stream
        except Exception as e:
            logger.debug(f"Microphone recovery failed: {e}. Retrying in 2 seconds...")
            time.sleep(2)
    return None

def recover_wake_detector(old_detector):
    logger.warning("Wake-word engine issue detected. Attempting to recover...")
    global _wake_healthy
    _wake_healthy = False
    while not shutdown_event.is_set():
        try:
            new_detector = LocalWakeWordDetector(
                model_path=wake_word_model_path,
                confidence_threshold=wake_word_threshold,
            )
            logger.info("Wake-word engine successfully recovered.")
            _wake_healthy = True
            return new_detector
        except Exception as e:
            logger.debug(f"Wake-word recovery failed: {e}. Retrying in 2 seconds...")
            time.sleep(2)
    return None


def clean_ansi(text: str) -> str:
    return re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").sub("", text)


_STOP_PHRASES = frozenset([
    "stop nova", "stop", "cancel", "never mind", "nevermind", "that's enough",
    "thats enough", "be quiet", "shut up", "pause", "wait", "hold on",
    "nova stop", "nova cancel",
])

_PREFIX_STOP_PHRASES = frozenset([
    "stop nova", "cancel", "never mind", "nevermind", "be quiet", "shut up",
    "nova stop", "nova cancel",
])

def _is_interrupt_phrase(text: str) -> bool:
    t = text.lower().strip().rstrip(".").rstrip(",")
    if t in _STOP_PHRASES:
        return True
    for phrase in _PREFIX_STOP_PHRASES:
        if t.startswith(phrase):
            return True
    return False


_interrupt_listener_active = threading.Event()

def _start_background_interrupt_listener(stream, stt_provider, calibrated_threshold: float) -> None:
    _interrupt_listener_active.set()

    def _listener():
        LISTEN_SECS = 2.0
        SILENCE_GATE = calibrated_threshold * 1.5

        while _interrupt_listener_active.is_set():
            try:
                n_samples = int(SAMPLE_RATE * LISTEN_SECS)
                with voice_config.stream_lock:
                    if stream is None or not stream.active:
                        break
                    try:
                        raw, _ = stream.read(n_samples)
                    except Exception:
                        break

                flat = raw.flatten()
                rms = float(np.sqrt(np.mean(flat * flat)))
                if rms < SILENCE_GATE:
                    continue

                audio_int16 = (np.clip(flat, -1.0, 1.0) * 32767).astype(np.int16)
                wav_io = io.BytesIO()
                with wave.open(wav_io, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(audio_int16.tobytes())
                wav_bytes = wav_io.getvalue()

                try:
                    heard = stt_provider.transcribe(wav_bytes, silent=True).strip()
                except Exception:
                    continue

                if heard and _is_interrupt_phrase(heard):
                    logger.debug(f"Background interrupt detected: '{heard}'")
                    voice_config.interrupt_speaking = True
                    _interrupt_listener_active.clear()
                    break
            except Exception as e:
                logger.debug(f"Background interrupt listener error: {e}")
                break

    t = threading.Thread(target=_listener, daemon=True)
    t.start()


def _stop_background_interrupt_listener() -> None:
    _interrupt_listener_active.clear()


def play_confirmation_sound() -> None:
    try:
        sr = 16000
        t1 = np.linspace(0, 0.08, int(sr * 0.08), endpoint=False)
        t2 = np.linspace(0, 0.12, int(sr * 0.12), endpoint=False)
        tone1 = 0.15 * np.sin(2 * np.pi * 880  * t1)
        tone2 = 0.15 * np.sin(2 * np.pi * 1320 * t2)
        pause = np.zeros(int(sr * 0.02))
        audio = np.concatenate([tone1, pause, tone2])
        fade_len = int(sr * 0.02)
        audio[-fade_len:] *= np.linspace(1.0, 0.0, fade_len)
        sd.play(audio, sr)
        sd.wait()
    except Exception as e:
        logger.debug(f"Confirmation sound failed: {e}")


def get_user_confirmation(prompt: str, stream, speech_threshold) -> bool:
    speak(prompt)
    try:
        time.sleep(0.2)
        response_audio = record_audio_from_stream(stream, calibrated_threshold=speech_threshold)
        stt_provider = get_stt_provider()
        response_text = stt_provider.transcribe(response_audio, silent=True).strip().lower()
        logger.debug(f"User confirmation response: '{response_text}'")
        positives = ("yes", "yeah", "yep", "sure", "correct", "do it", "play", "open", "go ahead")
        if any(p in response_text for p in positives):
            return True
    except Exception as e:
        logger.debug(f"Confirmation failed: {e}")
    return False


def check_long_running_action(dispatcher, actions: list, user_query: str) -> tuple[bool, str, str, str]:
    long_action = None
    for action_data in actions:
        name = action_data.get("action")
        handler = dispatcher.get(name)
        if handler:
            is_long = False
            if hasattr(handler, "is_long_running") and handler.is_long_running:
                is_long = True
            elif name in ("chromium_action", "browser_action", "search_package", "open_app", "install_package", 
                          "remove_package", "update_package", "git_command", "nix_shell", 
                          "adb_mirroring", "adb_device_op", "search_files", "locate_files"):
                is_long = True
            
            if is_long:
                long_action = action_data
                break
                
    if not long_action:
        return False, "", "", ""
        
    action_name = long_action.get("action", "")
    params = long_action
    user_query_lower = user_query.lower()
    
    subject = ""
    for k in ("app", "query", "search_query", "filename", "url", "package"):
        val = params.get(k)
        if val and isinstance(val, str) and val.strip():
            subject = val.strip()
            break
            
    if not subject:
        for marker in ("play ", "search for ", "search ", "find ", "open ", "launch ", "look for "):
            if marker in user_query_lower:
                idx = user_query_lower.find(marker) + len(marker)
                subject = user_query[idx:].strip().rstrip(".?")
                break

    subject_clean = subject
    if subject_clean.startswith(("http://", "https://")) or (any(ext in subject_clean.lower() for ext in (".com", ".org", ".net", ".io")) and "." in subject_clean):
        domain = subject_clean.replace("http://", "").replace("https://", "")
        if "/" in domain:
            domain = domain.split("/", 1)[0]
        domain = domain.replace("www.", "")
        subject_clean = domain.split(".")[0].capitalize()

    if subject_clean.lower() in ("youtube.com", "google.com", "youtube", "google"):
        for marker in ("play ", "search for ", "search ", "find ", "open ", "launch ", "look for "):
            if marker in user_query_lower:
                idx = user_query_lower.find(marker) + len(marker)
                subject_clean = user_query[idx:].strip().rstrip(".?")
                break

    if subject_clean.lower() == "chatgpt":
        subject_clean = "ChatGPT"

    if "youtube.com" in subject_clean or "youtube" in user_query_lower:
        subject_clean = re.sub(r"\s+on\s+youtube.*", "", subject_clean, flags=re.IGNORECASE).strip()
    
    ack_text = "Working on that."
    success_text = "Done."
    fail_text = "I couldn't complete that request."
    
    if action_name in ("browser_action", "chromium_action"):
        url = params.get("url", "").lower()
        operation = params.get("operation", "").lower()
        if "youtube" in url or "youtube" in user_query_lower or operation == "youtube_search":
            if subject_clean and subject_clean.lower() not in ("youtube", "http", "https"):
                acks = [
                    "Looking for that on YouTube.",
                    f"Searching YouTube for {subject_clean}.",
                    "One moment, finding it on YouTube.",
                    "Let me find that for you on YouTube.",
                    "I'll play that for you."
                ]
                successes = [
                    "Now playing. Enjoy!",
                    "Your music is ready.",
                    "I've started playback.",
                    f"Now playing {subject_clean}."
                ]
                ack_text = random.choice(acks)
                success_text = random.choice(successes)
            else:
                ack_text = "Opening YouTube."
                success_text = "YouTube is open."
            fail_text = "I couldn't find that song."
            
        elif "github" in url or "github" in user_query_lower:
            ack_text = "Opening GitHub."
            success_text = "GitHub is open."
            
        elif "google" in url or "google" in user_query_lower:
            if "search" in user_query_lower or "find" in user_query_lower:
                if subject_clean and subject_clean.lower() not in ("google", "http", "https"):
                    acks = [
                        f"Searching Google for {subject_clean}.",
                        f"Looking that up on Google.",
                        f"Let me search Google for {subject_clean}."
                    ]
                    ack_text = random.choice(acks)
                else:
                    ack_text = "Searching Google."
                success_text = "I found the results."
            else:
                ack_text = "Opening Google."
                success_text = "Google is ready."
        else:
            if subject_clean:
                ack_text = f"Opening {subject_clean}."
                success_text = f"{subject_clean} is ready."
            else:
                ack_text = "Opening the browser."
                success_text = "Browser is ready."
                
    elif action_name == "open_app":
        app = params.get("app", "")
        app_name = subject_clean or app
        if app_name:
            app_cap = app_name[0].upper() + app_name[1:] if app_name else ""
            acks = [
                f"Launching {app_cap}.",
                f"Opening {app_cap}.",
                f"One moment, starting {app_cap}."
            ]
            successes = [
                f"{app_cap} is ready.",
                f"{app_cap} is open."
            ]
            ack_text = random.choice(acks)
            success_text = random.choice(successes)
        else:
            ack_text = "Launching application."
            success_text = "Application is ready."
            
    elif action_name in ("google_search", "web_search", "search_package"):
        if subject_clean:
            acks = [
                f"Searching for {subject_clean}.",
                f"Looking that up.",
                f"Let me search for {subject_clean}."
            ]
            ack_text = random.choice(acks)
        else:
            ack_text = "Searching the web."
        success_text = "I found the results."
        
    elif action_name in ("search_files", "locate_files", "files_action"):
        if subject_clean:
            ack_text = f"Looking for your {subject_clean}."
            success_text = f"I found your {subject_clean}."
        else:
            ack_text = "Looking for your file."
            success_text = "I found your file."
            
    elif action_name in ("install_package", "remove_package", "update_package"):
        pkg = params.get("package", "")
        pkg_name = subject_clean or pkg
        if action_name == "install_package":
            ack_text = f"Installing {pkg_name}." if pkg_name else "Installing package."
            success_text = "Installation complete."
        elif action_name == "remove_package":
            ack_text = f"Uninstalling {pkg_name}." if pkg_name else "Removing package."
            success_text = "Package removed."
        else:
            ack_text = "Updating package."
            success_text = "Update complete."
            
    elif action_name == "git_command":
        ack_text = "Running git command."
        success_text = "Git command complete."
        
    elif action_name == "adb_mirroring":
        ack_text = "Connecting to device mirror..."
        success_text = "Device mirroring is ready."
        
    elif action_name == "adb_device_op":
        ack_text = "Connecting to Android device..."
        success_text = "Device command complete."

    return True, ack_text, success_text, fail_text


_WAKE_CHUNK   = 480
_WAKE_FRAME   = 1280
_WAKE_CAPTURE_SECS = 2.0


class CircularAudioBuffer:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.buffer = np.zeros(capacity, dtype=np.float32)
        self.index = 0
        self.filled = False

    def extend(self, data: np.ndarray):
        n = len(data)
        if n >= self.capacity:
            self.buffer[:] = data[-self.capacity:]
            self.index = 0
            self.filled = True
            return
        end = self.index + n
        if end <= self.capacity:
            self.buffer[self.index:end] = data
            self.index = end
        else:
            first_part = self.capacity - self.index
            self.buffer[self.index:] = data[:first_part]
            self.buffer[:n - first_part] = data[first_part:]
            self.index = n - first_part
            self.filled = True
        if self.index >= self.capacity:
            self.index = 0
            self.filled = True

    def get_latest(self) -> np.ndarray:
        if not self.filled:
            return self.buffer[:self.index].copy()
        return np.concatenate((self.buffer[self.index:], self.buffer[:self.index]))


def _wait_for_wake(
    stream: sd.InputStream,
    wake_detector: "LocalWakeWordDetector",
    noise_floor: float,
) -> tuple[bool, np.ndarray | None, float]:
    try:
        with voice_config.stream_lock:
            if stream.read_available > 0:
                stream.read(stream.read_available)
    except Exception:
        pass

    _cap_len = int(SAMPLE_RATE * _WAKE_CAPTURE_SECS)
    capture_buffer = CircularAudioBuffer(_cap_len)
    oww_accum = np.zeros(0, dtype=np.int16)

    _SOFTWARE_GAIN = 2.0
    _DETECT_THRESHOLD = 0.07
    _PATIENCE = 2
    _PATIENCE_WINDOW = 3
    score_history = collections.deque(maxlen=_PATIENCE_WINDOW)
    last_trigger = 0.0
    _WARMUP_FRAMES = 6
    warmup_remaining = _WARMUP_FRAMES

    while True:
        if shutdown_event.is_set() or _current_state == VoiceState.INACTIVE:
            return False, None, 0.0
        if voice_active_event.is_set():
            voice_active_event.clear()
            return True, None, 1.0

        try:
            with voice_config.stream_lock:
                recording, _ = stream.read(_WAKE_CHUNK)
        except Exception as e:
            logger.debug(f"Wake-loop read error: {e}")
            stream = recover_microphone(stream)
            if shutdown_event.is_set() or _current_state == VoiceState.INACTIVE:
                return False, None, 0.0
            continue

        flat = recording.flatten()
        aec = getattr(voice_config, "active_aec", None)
        if aec is not None:
            flat = aec.process(flat)
        capture_buffer.extend(flat)

        amplified = flat * _SOFTWARE_GAIN
        pcm_chunk = (np.clip(amplified, -1.0, 1.0) * 32767).astype(np.int16)
        oww_accum = np.concatenate((oww_accum, pcm_chunk))

        if len(oww_accum) < _WAKE_FRAME:
            continue

        oww_frame = oww_accum[:_WAKE_FRAME]
        oww_accum = oww_accum[_WAKE_FRAME:]

        try:
            predictions = wake_detector.model.predict(oww_frame)
        except Exception as e:
            logger.debug(f"OWW inference error: {e}")
            continue

        if warmup_remaining > 0:
            warmup_remaining -= 1
            continue

        score = predictions.get(wake_detector.model_name, 0.0)
        is_nova = False
        try:
            if hasattr(wake_detector, 'nova_detector'):
                latest_audio = capture_buffer.get_latest()
                if len(latest_audio) >= 8000:
                    is_nova = wake_detector.nova_detector.detect(latest_audio[-8000:], SAMPLE_RATE)
        except Exception as e:
            logger.debug(f"Nova detector failed: {e}")

        if is_nova:
            score = max(score, 0.95)

        score_history.append(score)

        if enable_debug:
            rms_val = float(np.sqrt(np.mean(flat * flat)))
            peak = float(np.max(np.abs(flat)))
            hits = sum(1 for s in score_history if s >= _DETECT_THRESHOLD)
            print(
                f"[DBG wake] score={score:.4f}  "
                f"thresh={_DETECT_THRESHOLD}  "
                f"hits={hits}/{_PATIENCE}  "
                f"rms={rms_val:.4f}  peak={peak:.4f}"
            )

        hits = sum(1 for s in score_history if s >= _DETECT_THRESHOLD)
        if hits >= _PATIENCE:
            now = time.time()
            if now - last_trigger < 1.5:
                score_history.clear()
                continue
            last_trigger = now
            score_history.clear()
            wake_audio = capture_buffer.get_latest()
            return True, wake_audio, float(score)


class VoiceLoopState:
    def __init__(self, diagnostics=None, working_memory=None):
        self.stt_provider = None
        self.verifier = None
        self.stream = None
        self.wake_detector = None
        self.adaptive_wake_ctrl = AdaptiveWakeController()
        self.fusion_engine = ConfidenceFusionEngine()
        self.quality_analyzer = AudioQualityAnalyzer()
        self.diagnostics = diagnostics if diagnostics is not None else VoiceDiagnosticsEngine()
        import nova.voice.config as _vc_cfg
        _vc_cfg.active_diagnostics = self.diagnostics

        from nova.core.memory import WorkingMemory
        self.working_memory = working_memory if working_memory is not None else WorkingMemory()
        self.use_wake_word = enable_wake_word
        self.noise_floor = VAD_THRESHOLD
        self.speech_threshold = VAD_THRESHOLD + NOISE_FLOOR_MARGIN
        self.calibrated = False
        self._greeted_this_activation = False
        self._first_ptt_since_activation = False
        self.last_command_snr = None
        self.last_clipping_pct = None
        self.skip_idle_wait = False
        self.hp_filter = None
        self.rnnoise = None
        self.agc = None
        self.vad = None
        self.aec = None
        self.current_state = VoiceState.INACTIVE
        self.last_printed_state = None


def infer_topic(intent: Optional[str], query: str, actions: list) -> Optional[str]:
    if not intent:
        return "general"
    if actions and isinstance(actions, list):
        action = actions[0]
        for param in ["query", "url", "app", "package", "text"]:
            if action.get(param):
                return f"{intent}: {action.get(param)}"
    return intent


def update_working_memory_after_turn(
    working_memory,
    user_message: str,
    assistant_reply: str,
    intent: Optional[str],
    topic: Optional[str]
) -> None:
    from nova.core.memory import Interaction
    prev_topic = working_memory.get("current_topic")
    prev_intent = working_memory.get("current_intent")

    working_memory.set("previous_topic", prev_topic)
    working_memory.set("previous_intent", prev_intent)
    working_memory.set("current_topic", topic)
    working_memory.set("current_intent", intent)
    working_memory.set("previous_command", user_message)
    working_memory.set("previous_assistant_reply", assistant_reply)

    interaction = Interaction(
        user_prompt=user_message,
        assistant_response=assistant_reply,
        intent=intent,
        timestamp=time.time()
    )
    working_memory.append_history(interaction)
    session_conv = list(working_memory.get("current_conversation") or [])
    session_conv.append(interaction)
    working_memory.set("current_conversation", session_conv)
    logger.info("Automatically updated working memory with user interaction details.")


def process_single_iteration(
    state: VoiceLoopState,
    ai_client,
    dispatcher,
    transition_to
) -> str:
    global _mic_healthy, _wake_healthy, _stt_healthy, _deferred_deactivate

    stt_provider = state.stt_provider
    verifier = state.verifier
    stream = state.stream
    wake_detector = state.wake_detector
    adaptive_wake_ctrl = state.adaptive_wake_ctrl
    fusion_engine = state.fusion_engine
    quality_analyzer = state.quality_analyzer
    diagnostics = state.diagnostics
    use_wake_word = state.use_wake_word
    noise_floor = state.noise_floor
    speech_threshold = state.speech_threshold
    calibrated = state.calibrated
    _greeted_this_activation = state._greeted_this_activation
    _first_ptt_since_activation = state._first_ptt_since_activation
    last_command_snr = state.last_command_snr
    last_clipping_pct = state.last_clipping_pct
    skip_idle_wait = state.skip_idle_wait
    hp_filter = state.hp_filter
    rnnoise = state.rnnoise
    agc = state.agc
    vad = state.vad
    aec = state.aec
    last_printed_state = state.last_printed_state

    def save_state():
        state.stt_provider = stt_provider
        state.verifier = verifier
        state.stream = stream
        state.wake_detector = wake_detector
        state.noise_floor = noise_floor
        state.speech_threshold = speech_threshold
        state.calibrated = calibrated
        state._greeted_this_activation = _greeted_this_activation
        state._first_ptt_since_activation = _first_ptt_since_activation
        state.last_command_snr = last_command_snr
        state.last_clipping_pct = last_clipping_pct
        state.skip_idle_wait = skip_idle_wait
        state.hp_filter = hp_filter
        state.rnnoise = rnnoise
        state.agc = agc
        state.vad = vad
        state.aec = aec
        state.last_printed_state = last_printed_state

    quality_metrics = None
    speaker_score = None
    cmd_start = time.time()
    assistant_reply = ""

    if _current_state in (VoiceState.INACTIVE, VoiceState.TEXT_MODE):
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            stream = None
            voice_config.active_stream = None
            _mic_healthy = False
        _greeted_this_activation = False
        _first_ptt_since_activation = True
        
        while _current_state in (VoiceState.INACTIVE, VoiceState.TEXT_MODE) and not shutdown_event.is_set():
            if voice_active_event.is_set():
                voice_active_event.clear()
                transition_to(VoiceState.VOICE_IDLE)
                break
            time.sleep(0.1)
        save_state()
        return "continue"

    try:
        state.working_memory.set("listening_state", "idle")
        state.working_memory.set("wake_word_activation", False)
        state.working_memory.set("recognition_confidence", 0.0)
        state.working_memory.set("current_speaker", None)
        state.working_memory.set("final_transcription", None)
    except Exception as e:
        logger.debug(f"Failed to reset turn memory: {e}")

    if _current_state == VoiceState.VOICE_IDLE:
        if stt_provider is None:
            try:
                stt_provider = get_stt_provider()
                _stt_healthy = True
            except Exception as e:
                logger.error(f"Failed to initialize STT provider: {e}")
                _stt_healthy = False
                stt_provider = None

        if verifier is None and enable_speaker_verification:
            verifier = SpeakerVerifier(
                embedding_path=speaker_embedding_path,
                threshold=speaker_similarity_threshold,
            )
            if not verifier.available:
                print_warning("resemblyzer not installed — speaker verification disabled.")
                verifier = None
            elif not verifier.has_profile():
                print_warning('No enrolled voice profile found. Using wake-word only. Run "nova voice-setup" to enroll.')
                verifier = None

        if stream is None:
            try:
                if not sd.query_devices(kind="input"):
                    raise RuntimeError("No input device found.")
                stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32")
                stream.start()
                _mic_healthy = True
                voice_config.active_stream = stream
            except Exception as e:
                print_error(f"Failed to open microphone: {e}")
                _mic_healthy = False
                transition_to(VoiceState.INACTIVE)
                save_state()
                return "continue"

        if not calibrated:
            try:
                calib_n = int(SAMPLE_RATE * AMBIENT_CALIBRATION_DURATION)
                with voice_config.stream_lock:
                    calib_audio, _ = stream.read(calib_n)
                calibrator = AmbientCalibrator()
                calibrator.calibrate(calib_audio)
                noise_floor = calibrator.noise_floor
                speech_threshold = calibrator.speech_threshold
                if noise_floor > 0.5:
                    speech_threshold = 0.02
                calibrated = True
            except Exception as e:
                logger.debug(f"Calibration error: {e}")
                print_warning("Calibration failed — using defaults.")
                calibrated = True

        if hp_filter is None:
            try:
                aec = AecProcessor() if voice_config.ENABLE_ECHO_CANCEL else None
                voice_config.active_aec = aec
                hp_filter = HighPassFilter(cutoff=HIGHPASS_CUTOFF, fs=SAMPLE_RATE) if ENABLE_HIGHPASS_FILTER else None
                rnnoise = RNNoiseWrapper() if ENABLE_NOISE_SUPPRESSION else None
                agc = AutomaticGainControl() if ENABLE_AGC else None
                vad = WebRTCVoiceActivityDetector(aggressiveness=VAD_AGGRESSIVENESS, default_threshold=speech_threshold) if ENABLE_VAD else None
            except Exception as e:
                logger.debug(f"Failed to initialize persistent preprocessors: {e}")

        use_wake_word = enable_wake_word
        if wake_detector is None and use_wake_word:
            try:
                wake_detector = LocalWakeWordDetector(
                    model_path=wake_word_model_path,
                    confidence_threshold=wake_word_threshold,
                )
                _wake_healthy = True
                voice_config.active_wake_detector = wake_detector
            except Exception as e:
                logger.debug(f"Wake-engine load error: {e}")
                _wake_healthy = False
                use_wake_word = False

        if not _greeted_this_activation:
            _greeted_this_activation = True
            try:
                greeting_text = get_activation_greeting()
                speak(greeting_text)
                time.sleep(0.3)
                if stream is not None:
                    with voice_config.stream_lock:
                        if stream.read_available > 0:
                            stream.read(stream.read_available)
            except Exception:
                pass

    if not skip_idle_wait:
        if verifier is not None:
            verifier.clear_pending_adaptation()
        
        try:
            adapted = adaptive_wake_ctrl.adapt(
                noise_floor,
                signal_quality_snr=last_command_snr,
                clipping_pct=last_clipping_pct
            )
            if wake_detector is not None:
                wake_detector.confidence_threshold = adapted["wake_threshold"]
            if verifier is not None:
                verifier._threshold = adapted["speaker_threshold"]
        except Exception as adapt_err:
            logger.debug(f"Threshold adaptation error: {adapt_err}")

        if use_wake_word:
            transition_to(VoiceState.VOICE_IDLE)
            if last_printed_state != VoiceState.VOICE_IDLE:
                print_info(f'👂 Waiting for "{wake_word_phrase}"')
                last_printed_state = VoiceState.VOICE_IDLE
            detected, wake_audio, wake_score = _wait_for_wake(stream, wake_detector, noise_floor)
            if _current_state == VoiceState.INACTIVE:
                save_state()
                return "continue"
            if not detected:
                if shutdown_event.is_set():
                    save_state()
                    return "break"
                save_state()
                return "continue"

            try:
                try:
                    from nova.dashboard.event_bus import emit
                    emit("wake_word_detected", module="voice", status="success", metadata={"detector": "OpenWakeWord"})
                except Exception:
                    pass

                transition_to(VoiceState.WAKE_DETECTED)
                if wake_audio is not None:
                    quality_metrics = quality_analyzer.analyze(wake_audio)
                    vad_frames = 0
                    total_frames = len(wake_audio) // 480
                    if total_frames > 0 and vad is not None:
                        for i in range(total_frames):
                            chunk = wake_audio[i*480 : (i+1)*480]
                            if vad.is_speech(chunk, SAMPLE_RATE):
                                vad_frames += 1
                        vad_score = vad_frames / total_frames
                    else:
                        vad_score = None
                        
                    speaker_score = None
                    if verifier is not None:
                        _, speaker_score = verifier.verify(wake_audio, SAMPLE_RATE)
                        
                    _raw_wake = wake_score
                    _wake_detect_thresh = 0.07
                    if _raw_wake >= _wake_detect_thresh:
                        normalized_wake = 0.70 + 0.30 * min(1.0, (_raw_wake - _wake_detect_thresh) / (1.0 - _wake_detect_thresh))
                    else:
                        normalized_wake = _raw_wake

                    normalized_speaker = speaker_score
                    if speaker_score is not None and verifier is not None:
                        _spk_thresh = verifier._threshold
                        if speaker_score >= _spk_thresh:
                            normalized_speaker = 0.70 + 0.30 * min(1.0, (speaker_score - _spk_thresh) / (1.0 - _spk_thresh))
                        else:
                            normalized_speaker = 0.70 * (speaker_score / _spk_thresh) if _spk_thresh > 0 else speaker_score

                    fused_score = fusion_engine.fuse(
                        wake_score=normalized_wake,
                        speaker_score=normalized_speaker,
                        vad_score=vad_score,
                        audio_quality=quality_metrics["overall_quality"],
                        noise_level=quality_metrics["background_noise"]
                    )
                    
                    if enable_debug:
                        logger.debug(
                            f"[FUSION] raw_wake={wake_score:.3f} norm_wake={normalized_wake:.3f} "
                            f"raw_speaker={str(speaker_score)} norm_speaker={str(normalized_speaker)} "
                            f"vad={str(vad_score)} quality={quality_metrics['overall_quality']:.3f} "
                            f"noise={quality_metrics['background_noise']:.5f} -> fused={fused_score:.3f}"
                        )
                        print_info(f"Fused confidence score: {fused_score:.3f}")
                        
                    fusion_threshold = getattr(voice_config, "FUSION_TRIGGER_THRESHOLD", 0.50)

                    if getattr(voice_config, "ENABLE_VOICE_DEBUG", False):
                        wake_threshold = wake_detector.confidence_threshold if wake_detector is not None else getattr(voice_config, "WAKE_WORD_THRESHOLD", 0.30)
                        speaker_threshold = verifier._threshold if verifier is not None else getattr(voice_config, "speaker_similarity_threshold", 0.75)
                        decision = "ACCEPTED" if fused_score >= fusion_threshold else "REJECTED"
                        
                        reason = "N/A"
                        if decision == "REJECTED":
                            if wake_score < wake_threshold:
                                reason = "Wake-word confidence too low"
                            elif verifier is not None and speaker_score is not None and speaker_score < speaker_threshold:
                                reason = "Speaker similarity too low"
                            else:
                                reason = "Overall fusion score too low"

                        wake_val = f"{wake_score:.4f}"
                        speaker_val = f"{speaker_score:.4f}" if speaker_score is not None else "N/A"
                        vad_val = f"{vad_score:.4f}" if vad_score is not None else "N/A"
                        quality_val = f"{quality_metrics.get('overall_quality'):.4f}" if quality_metrics else "N/A"
                        noise_val = f"{quality_metrics.get('background_noise'):.6f}" if quality_metrics else "N/A"
                        
                        print("\n--- Voice Debug Mode ---")
                        print(f"Wake-word model score           : {wake_val}")
                        print(f"Speaker verification similarity : {speaker_val}")
                        print(f"Speaker threshold               : {speaker_threshold:.4f}")
                        print(f"Fusion inputs                   : wake={wake_val}, speaker={speaker_val}, vad={vad_val}, quality={quality_val}, noise={noise_val}")
                        print(f"Final fusion score              : {fused_score:.4f}")
                        print(f"Fusion threshold                : {fusion_threshold:.4f}")
                        print(f"Ambient noise estimate          : {f'{noise_floor:.6f}' if noise_floor is not None else 'N/A'}")
                        print(f"Decision                        : {decision}")
                        print(f"Exact reason for rejection      : {reason}")
                        print("------------------------\n")
                        
                    if fused_score < fusion_threshold:
                        print_warning(
                            f"Trigger rejected by Confidence Fusion Engine (score {fused_score:.2f} < {fusion_threshold}) — continuing to listen."
                        )
                        diagnostics.record_audio_quality(quality_metrics)
                        save_state()
                        return "continue"

                    speech_start_t = getattr(wake_detector, "last_speech_start_time_abs", None)
                    if speech_start_t is not None:
                        wake_latency_ms = (time.time() - speech_start_t) * 1000.0
                    else:
                        wake_latency_ms = 800.0
                        if hasattr(wake_detector, "diagnostics_history") and wake_detector.diagnostics_history:
                            last_diag = wake_detector.diagnostics_history[-1]
                            if last_diag.get("event") == "wake_trigger":
                                wake_latency_ms = last_diag.get("speaking_latency_ms", 800.0)
                    
                    diagnostics.record_wake_success(score=wake_score, latency_ms=wake_latency_ms)
                    diagnostics.record_audio_quality(quality_metrics)
                    diagnostics.record_noise_sample(quality_metrics["background_noise"])

                    try:
                        state.working_memory.set("wake_word_activation", True)
                        state.working_memory.set("listening_state", "listening")
                        state.working_memory.set("recognition_confidence", fused_score)
                        speaker_status = "verified" if (speaker_score is not None and verifier is not None and speaker_score >= verifier._threshold) else "unknown"
                        state.working_memory.set("current_speaker", speaker_status)
                        try:
                            state.working_memory.history_manager.add_entry(
                                "voice_event",
                                f"Wake word detected (confidence: {fused_score:.2f})",
                                {"confidence": fused_score, "speaker": speaker_status}
                            )
                        except Exception:
                            pass
                    except Exception as e:
                        logger.debug(f"Failed to update working memory after wake: {e}")

                if enable_debug:
                    print_success("Wake Detected")
                if confirmation_sound:
                    play_confirmation_sound()
                    time.sleep(0.15)

                try:
                    with voice_config.stream_lock:
                        if stream.read_available > 0:
                            stream.read(stream.read_available)
                except Exception:
                    pass
            except Exception as wake_err:
                logger.error(f"Exception in wake processing: {wake_err}")
                try:
                    diagnostics.record_missed_wake(wake_score=wake_score, noise_floor=noise_floor)
                except Exception:
                    pass
                transition_to(VoiceState.VOICE_IDLE)
                save_state()
                return "continue"
        else:
            transition_to(VoiceState.PUSH_TO_TALK)
            try:
                state.working_memory.set("listening_state", "listening")
                state.working_memory.set("recognition_confidence", 1.0)
                state.working_memory.set("current_speaker", "verified")
                try:
                    state.working_memory.history_manager.add_entry("voice_event", "Push-to-Talk activation triggered")
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"Failed to set PTT memory properties: {e}")
            try:
                input("Press ENTER to record a command...")
            except KeyboardInterrupt:
                save_state()
                return "break"
            except EOFError:
                logger.debug("PTT: No TTY detected — daemon mode, shortcut is the trigger.")
                if _first_ptt_since_activation:
                    _first_ptt_since_activation = False
                else:
                    while not shutdown_event.is_set() and _current_state not in (VoiceState.INACTIVE, VoiceState.TEXT_MODE):
                        if voice_active_event.is_set():
                            voice_active_event.clear()
                            break
                        time.sleep(0.1)
                    else:
                        save_state()
                        return "break"
    else:
        skip_idle_wait = False

    transition_to(VoiceState.LISTENING)
    if last_printed_state != VoiceState.LISTENING:
        print_info("🎤 Listening...")
        last_printed_state = VoiceState.LISTENING
        
    try:
        from nova.dashboard.event_bus import emit
        emit("speech_started", module="voice", status="running")
    except Exception:
        pass
        
    cmd_start   = time.time()
    record_start = time.time()
    muted = False
    try:
        subprocess.run(
            ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        muted = True
    except Exception:
        pass

    command_wav = None
    try:
        command_wav = record_audio_from_stream(
            stream, calibrated_threshold=speech_threshold,
            hp_filter=hp_filter, rnnoise=rnnoise, agc=agc, vad=vad, aec=aec
        )
    except Exception as e:
        print_error(f"Recording failed: {e}")
    finally:
        if muted:
            try:
                subprocess.run(
                    ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    if command_wav is None:
        try:
            from nova.dashboard.event_bus import emit
            emit("speech_finished", module="voice", status="failed", metadata={"reason": "recording_failed"})
        except Exception:
            pass
        save_state()
        return "continue"

    record_dur = time.time() - record_start
    try:
        from nova.dashboard.event_bus import emit
        emit("speech_finished", module="voice", status="success", metadata={"duration": record_dur})
    except Exception:
        pass

    if isinstance(command_wav, bytes):
        try:
            with wave.open(io.BytesIO(command_wav), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            diag = AudioDiagnostics(SAMPLE_RATE)
            m = diag.measure(samples)
            last_command_snr = m.get('snr_db', None)
            last_clipping_pct = m.get('clipping_pct', None)
        except Exception as diag_err:
            logger.debug(f"Diagnostics measurement failed: {diag_err}")

    transition_to(VoiceState.TRANSCRIBING)
    if enable_debug:
        print_info("🧠 Transcribing")
    try:
        from nova.dashboard.event_bus import emit
        emit("transcription_partial", module="stt", status="running")
    except Exception:
        pass

    t0 = time.time()
    try:
        text = stt_provider.transcribe(command_wav, silent=True)
        _stt_healthy = True
    except Exception as e:
        print_error(f"Transcription failed: {e}")
        try:
            from nova.dashboard.event_bus import emit
            emit("transcription_complete", module="stt", status="failed", metadata={"error": str(e)})
        except Exception:
            pass

        logger.warning(f"STT failed: {e}. Re-initializing STT provider...")
        try:
            stt_provider = get_stt_provider()
            _stt_healthy = True
        except Exception as stt_err:
            logger.error(f"Failed to re-initialize STT provider: {stt_err}")
            _stt_healthy = False
        save_state()
        return "continue"
    transcribe_dur = time.time() - t0

    if not text:
        print_warning("I didn't catch that.")
        last_printed_state = VoiceState.VOICE_IDLE
        save_state()
        return "continue"

    print_success(f'Heard: "{text}"')
    try:
        state.working_memory.set("final_transcription", text)
        try:
            state.working_memory.history_manager.add_entry(
                "voice_event",
                f"Speech transcribed: '{text}'",
                {"transcription": text}
            )
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"Failed to set final_transcription: {e}")

    if text.lower().strip().rstrip(".") in ("exit", "quit", "goodbye"):
        transition_to(VoiceState.SPEAKING)
        assistant_reply = "Goodbye!"
        speak(assistant_reply)
        try:
            update_working_memory_after_turn(
                working_memory=state.working_memory,
                user_message=text,
                assistant_reply=assistant_reply,
                intent="exit",
                topic="session_end"
            )
        except Exception as wm_err:
            logger.debug(f"Failed to update working memory: {wm_err}")
        save_state()
        return "break"

    if _is_interrupt_phrase(text):
        print_info("🛑 Stop command heard — going back to listening.")
        transition_to(VoiceState.SPEAKING)
        assistant_reply = "Sure, I'm listening."
        speak(assistant_reply)
        try:
            update_working_memory_after_turn(
                working_memory=state.working_memory,
                user_message=text,
                assistant_reply=assistant_reply,
                intent="stop",
                topic="conversation_control"
            )
        except Exception as wm_err:
            logger.debug(f"Failed to update working memory: {wm_err}")
        last_printed_state = VoiceState.VOICE_IDLE
        if confirmation_sound:
            play_confirmation_sound()
        skip_idle_wait = True
        save_state()
        return "continue"

    transition_to(VoiceState.EXECUTING)
    if last_printed_state != VoiceState.EXECUTING:
        print_info("▶ Executing...")
        last_printed_state = VoiceState.EXECUTING

    from nova.core.executor import CommandExecutor
    CommandExecutor.clear_last_commands()

    from nova.spelling import correct_query_spelling, correct_action_data
    import nova.spelling as spelling
    corrected = correct_query_spelling(text)

    try:
        from nova.dashboard.event_bus import emit
        emit("transcription_complete", module="stt", status="success", metadata={"raw_text": text, "corrected_text": corrected})
    except Exception:
        pass

    requires_confirm = False
    confirm_prompt = ""
    if hasattr(stt_provider, "last_avg_logprob") and stt_provider.last_avg_logprob < -0.85:
        requires_confirm = True
        confirm_prompt = f"Did you mean '{corrected}'?"
    if spelling.last_correction_applied:
        try:
            from nova.dashboard.event_bus import emit
            emit("memory_indexed", module="memory", status="success", metadata={
                "action": "spelling_correction",
                "raw_query": text,
                "corrected_query": corrected,
                "prompt": spelling.correction_prompt
            })
        except Exception:
            pass
        requires_confirm = True
        confirm_prompt = spelling.correction_prompt

    if requires_confirm and confirm_prompt:
        confirmed = get_user_confirmation(confirm_prompt, stream, speech_threshold)
        if not confirmed:
            assistant_reply = "Cancelled."
            speak(assistant_reply)
            try:
                update_working_memory_after_turn(
                    working_memory=state.working_memory,
                    user_message=text,
                    assistant_reply=assistant_reply,
                    intent="confirm_cancel",
                    topic="confirmation"
                )
            except Exception as wm_err:
                logger.debug(f"Failed to update working memory: {wm_err}")
            last_printed_state = VoiceState.VOICE_IDLE
            save_state()
            return "continue"

    try:
        from nova.dashboard.event_bus import emit
        emit("llm_started", module="llm", status="running", metadata={"query": corrected})
    except Exception:
        pass

    try:
        raw_response = ai_client.parse_intent(corrected)
        try:
            from nova.dashboard.event_bus import emit
            emit("llm_finished", module="llm", status="success", metadata={"query": corrected, "response": raw_response})
        except Exception:
            pass
    except Exception as e:
        print_error(f"Intent parsing failed: {e}")
        try:
            from nova.dashboard.event_bus import emit
            emit("llm_finished", module="llm", status="failed", metadata={"query": corrected, "error": str(e)})
        except Exception:
            pass
        save_state()
        return "continue"

    if not raw_response:
        print_error("All AI APIs failed. Check your API keys and network.")
        save_state()
        return "continue"

    from nova.parser import parse_and_validate_action
    try:
        actions = parse_and_validate_action(raw_response)
    except Exception as e:
        print_error(f"Action validation failed: {e}")
        save_state()
        return "continue"

    if not actions:
        print_error("Could not parse an action from the AI response.")
        save_state()
        return "continue"

    success_msgs = []
    is_long, ack_text, success_text, fail_text = check_long_running_action(dispatcher, actions, text)
    
    ack_thread = None
    if is_long:
        ack_thread = threading.Thread(target=speak, args=(ack_text,))
        ack_thread.start()

    _stop_background_interrupt_listener()
    if stt_provider is not None and stream is not None:
        _start_background_interrupt_listener(stream, stt_provider, speech_threshold)

    from nova.ai.planner import Goal
    from nova.ai.reasoning import route_query_to_planner_pipeline
    from nova.core.state import StateManager
    
    approval_required = not StateManager.is_autonomous()
    goal = Goal(description=corrected)
    goal.metadata = {"actions": actions}
    
    try:
        result_message = route_query_to_planner_pipeline(
            query=corrected,
            working_memory=state.working_memory,
            dispatcher=dispatcher,
            approval_required=approval_required,
            actions=actions
        )
        if "error" in result_message.lower() or "failed" in result_message.lower():
            print_error(result_message)
        else:
            print_success(result_message)
            success_msgs.append(result_message)
    except Exception as e:
        print_error(f"Plan execution failed: {e}")

    if verifier is not None:
        verifier.commit_adaptation()

    total_dur = time.time() - cmd_start
    logger.info(f"Record: {record_dur:.2f}s | Transcribe: {transcribe_dur:.2f}s | Total: {total_dur:.2f}s")

    if ack_thread:
        ack_thread.join(timeout=2.0)

    _turn_tts_ms = 0.0
    if is_long:
        if success_msgs:
            transition_to(VoiceState.SPEAKING)
            last_printed_state = VoiceState.SPEAKING
            assistant_reply = success_text
            _tts_start = time.perf_counter()
            speak(success_text)
            _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0
        else:
            transition_to(VoiceState.SPEAKING)
            last_printed_state = VoiceState.SPEAKING
            assistant_reply = fail_text
            _tts_start = time.perf_counter()
            speak(fail_text)
            _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0
    else:
        if success_msgs:
            transition_to(VoiceState.SPEAKING)
            last_printed_state = VoiceState.SPEAKING
            spoken = " ".join(clean_ansi(m) for m in success_msgs)
            user_text_lower = text.lower()
            read_full_phrases = [
                "read everything", "read the full response", "read the complete response", 
                "read full response", "read all", "read full text", "read the full text"
            ]
            read_full = any(phrase in user_text_lower for phrase in read_full_phrases)
            
            if read_full:
                assistant_reply = spoken
                _tts_start = time.perf_counter()
                speak(spoken)
                _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0
            else:
                try:
                    spoken_summary = ai_client.generate_tts_summary(text, spoken)
                except Exception as e:
                    logger.debug(f"Failed to generate spoken summary: {e}")
                    spoken_summary = spoken
                assistant_reply = spoken_summary
                _tts_start = time.perf_counter()
                speak(spoken_summary)
                _turn_tts_ms = (time.perf_counter() - _tts_start) * 1000.0

    if enable_debug:
        print_success("✔ Finished")

    try:
        _turn_e2e_ms = (time.time() - cmd_start) * 1000.0
        _turn_stt_ms = transcribe_dur * 1000.0
        _turn_quality = quality_metrics.get("overall_quality", 1.0) if quality_metrics is not None else 1.0
        _turn_noise   = quality_metrics.get("background_noise", 0.0) if quality_metrics is not None else 0.0
        _turn_speaker = float(speaker_score) if speaker_score is not None else None
        diagnostics.record_turn(
            latency_ms=_turn_e2e_ms,
            stt_latency_ms=_turn_stt_ms,
            tts_latency_ms=_turn_tts_ms,
            audio_quality=_turn_quality,
            speaker_confidence=_turn_speaker,
            noise_floor=_turn_noise,
        )
    except Exception as _diag_err:
        logger.debug(f"Diagnostics record_turn failed: {_diag_err}")

    try:
        intent = actions[0].get("action") if actions else None
        topic = infer_topic(intent, corrected, actions)
        update_working_memory_after_turn(
            working_memory=state.working_memory,
            user_message=text,
            assistant_reply=assistant_reply,
            intent=intent,
            topic=topic
        )
    except Exception as wm_err:
        logger.debug(f"Failed to update working memory: {wm_err}")

    _stop_background_interrupt_listener()

    if voice_config.interrupt_speaking:
        voice_config.interrupt_speaking = False
        print_success("Nova interrupted. Listening...")
        if confirmation_sound:
            play_confirmation_sound()
        skip_idle_wait = True
        save_state()
        return "continue"

    try:
        time.sleep(0.8)
        if stream is not None:
            with voice_config.stream_lock:
                if stream.read_available > 0:
                    stream.read(stream.read_available)
    except Exception:
        pass

    if _deferred_deactivate:
        _deferred_deactivate = False
        print_info("Nova has stopped listening.")
        transition_to(VoiceState.INACTIVE)

    save_state()
    return "continue"


def run_voice_loop(ai_client, dispatcher, interactive=False, working_memory=None) -> str:
    global _mic_healthy, _wake_healthy, _stt_healthy, _deferred_deactivate

    state = VoiceLoopState(working_memory=working_memory)
    try:
        state.working_memory.set("voice_session_state", "active")
        try:
            state.working_memory.history_manager.add_entry("voice_event", "Voice session started")
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"Failed to set voice_session_state: {e}")

    try:
        from nova.browser.manager import BrowserManager
        BrowserManager._working_memory = state.working_memory
    except Exception as e:
        logger.debug(f"Failed to inject working memory to BrowserManager: {e}")

    if dispatcher:
        for action in dispatcher.values():
            try:
                action.working_memory = state.working_memory
            except Exception:
                pass

    def transition_to(new_state: VoiceState, detail: str = ""):
        state.current_state = new_state
        global _current_state
        _current_state = new_state
        logger.debug(f"[STATE] Transitioned to {new_state.name}{f' ({detail})' if detail else ''}")
        try:
            from nova.dashboard.event_bus import emit
            emit("voice_state_change", module="voice", status="running", metadata={"state": new_state.name, "detail": detail})
        except Exception:
            pass

    if interactive:
        transition_to(VoiceState.VOICE_IDLE)
    else:
        transition_to(VoiceState.INACTIVE)
    print_success("Voice Mode Ready")

    try:
        while True:
            if shutdown_event.is_set():
                break
            action = process_single_iteration(state, ai_client, dispatcher, transition_to)
            if action == "break":
                break
            elif action == "continue":
                continue
            elif action in ("menu", "exit"):
                return action
    except KeyboardInterrupt:
        print()

    transition_to(VoiceState.SHUTDOWN)
    _mic_healthy = False

    try:
        state.diagnostics.flush_to_disk()
    except Exception:
        pass

    if state.stream is not None:
        try:
            state.stream.stop()
            state.stream.close()
        except Exception:
            pass
        voice_config.active_stream = None

    if state.rnnoise:
        try:
            state.rnnoise.destroy()
        except Exception:
            pass

    if state.aec:
        try:
            state.aec.destroy()
        except Exception:
            pass

    print_info("Voice Mode Closed")
    try:
        state.working_memory.set("voice_session_state", "inactive")
        state.working_memory.set("listening_state", "idle")
        try:
            state.working_memory.history_manager.add_entry("voice_event", "Voice session stopped")
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"Failed to reset voice properties: {e}")
    return "menu"


def run_voice_self_test() -> None:
    import sys
    import platform
    from nova.voice.config import DIAGNOSTICS_LOG_PATH
    overall_pass = True

    print(f"\n{COLOR_BOLD}=== NOVA VOICE SUBSYSTEM SELF-TEST ==={COLOR_RESET}\n")

    # 1. Dependency Check
    print_info("Checking python module dependencies...")
    deps = [
        "openwakeword", "onnxruntime", "sounddevice", "numpy", "scipy",
        "webrtcvad", "psutil", "resemblyzer", "faster_whisper",
    ]
    dep_all_pass = True
    for dep in deps:
        try:
            mod = __import__(dep)
            print_success(f"  - {dep}: PASS (v{getattr(mod, '__version__', 'installed')})")
        except ImportError as e:
            dep_all_pass = False
            print_error(f"  - {dep}: FAIL (ModuleNotFoundError: {e})")

    print(f"✓ Dependency Check: {'PASS' if dep_all_pass else 'FAIL'}")
    if not dep_all_pass:
        overall_pass = False
    print("-" * 50)

    # 2. Microphone Check
    print_info("Checking microphone device accessibility...")
    try:
        device_info = sd.query_devices(kind='input')
        if not device_info:
            mic_status, mic_msg = "FAIL", "No input device detected."
        else:
            name = device_info.get("name")
            sr = device_info.get("default_samplerate")
            ch = device_info.get("max_input_channels")
            with sd.InputStream(samplerate=16000, channels=1, dtype='float32') as stream:
                pass
            mic_status, mic_msg = "PASS", f"Detected: '{name}' | Default SR: {sr}Hz | Input Channels: {ch}"
    except Exception as e:
        mic_status, mic_msg = "FAIL", f"Microphone error: {e}"

    if mic_status == "FAIL":
        overall_pass = False
        print_error(f"  - {mic_msg}")
    else:
        print_success(f"  - {mic_msg}")
    print(f"✓ Microphone Check: {mic_status}")
    print("-" * 50)

    # 3. Model Check
    print_info("Checking wake-word model existence and loading...")
    try:
        import openwakeword
        package_dir = os.path.dirname(openwakeword.__file__)
        resources_model_path = os.path.join(package_dir, "resources", "models", "hey_nova_v0.1.onnx")
        if not os.path.exists(resources_model_path):
            model_status, model_msg = "FAIL", f"hey_nova_v0.1.onnx not found at resource path: {resources_model_path}"
        else:
            from openwakeword.model import Model
            model = Model(wakeword_model_paths=[resources_model_path])
            model_status, model_msg = "PASS", f"Path resolved & loaded successfully:\n{resources_model_path}"
    except Exception as e:
        model_status, model_msg = "FAIL", f"Model loading failure: {e}"

    if model_status == "FAIL":
        overall_pass = False
        print_error(f"  - {model_msg}")
    else:
        print_success(f"  - {model_msg}")
    print(f"✓ Model Check: {model_status}")
    print("-" * 50)

    # 4. Inference Check
    print_info("Running dummy audio inference on OpenWakeWord...")
    try:
        import openwakeword
        from openwakeword.model import Model
        package_dir = os.path.dirname(openwakeword.__file__)
        model_path = os.path.join(package_dir, "resources", "models", "hey_nova_v0.1.onnx")
        model = Model(wakeword_model_paths=[model_path])
        model_name = os.path.splitext(os.path.basename(model_path))[0]
        dummy_pcm = np.zeros(1280, dtype=np.int16)
        predictions = model.predict(dummy_pcm)
        if model_name not in predictions:
            inf_status, inf_msg = "FAIL", f"Model name key '{model_name}' not found in predictions dictionary: {predictions}"
        else:
            score = predictions.get(model_name, 0.0)
            inf_status, inf_msg = "PASS", f"Inference completed. Score: {score} | Predictions: {predictions}"
    except Exception as e:
        inf_status, inf_msg = "FAIL", f"Inference check error: {e}"

    if inf_status == "FAIL":
        overall_pass = False
        print_error(f"  - {inf_msg}")
    else:
        print_success(f"  - {inf_msg}")
    print(f"✓ Inference Check: {inf_status}")
    print("-" * 50)

    # 5. Signal Check
    print_info("Testing live audio signal capture...")
    try:
        duration = 2.0
        print_info(f"🎤 Recording a {duration}-second audio clip to verify live microphone signal. Please speak...")
        recording = sd.rec(int(duration * 16000), samplerate=16000, channels=1, dtype='float32')
        sd.wait()
        rms = float(np.sqrt(np.mean(np.square(recording))))
        details = f"Frame size: {len(recording)} | RMS Amplitude: {rms:.6f}"
        if rms == 0.0:
            sig_status, sig_msg = "FAIL", f"Captured audio is completely silent. Check mic. Details: {details}"
        else:
            sig_status, sig_msg = "PASS", f"Audio signal verified successfully. Details: {details}"
    except Exception as e:
        sig_status, sig_msg = "FAIL", f"Signal check failure: {e}"

    if sig_status == "FAIL":
        overall_pass = False
        print_error(f"  - {sig_msg}")
    else:
        print_success(f"  - {sig_msg}")
    print(f"✓ Wake-Word Signal Check: {sig_status}")
    print("-" * 50)

    # 6. STT Connection Check
    print_info("Verifying STT pipeline...")
    try:
        stt_provider = get_stt_provider()
        dummy_pcm = np.zeros(16000, dtype=np.int16)
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(dummy_pcm.tobytes())
        wav_bytes = wav_io.getvalue()
        provider_name = "Local Whisper" if "WhisperSTTProvider" in str(type(stt_provider)) else "Remote STT"
        print_info(f"📤 Sending silent query to {provider_name} to verify pipeline...")
        transcription = stt_provider.transcribe(wav_bytes, silent=True)
        stt_status, stt_msg = "PASS", f"({provider_name}) Transcription returned: '{transcription}'"
    except Exception as e:
        stt_status, stt_msg = "FAIL", f"STT pipeline check failure: {e}"

    if stt_status == "FAIL":
        overall_pass = False
        print_error(f"  - {stt_msg}")
    else:
        print_success(f"  - {stt_msg}")
    print(f"✓ STT Check: {stt_status}")
    print("-" * 50)

    # 7. RNNoise Check
    print_info("Verifying RNNoise denoiser...")
    try:
        rn = RNNoiseWrapper()
        if not rn.is_available():
            rn_status, rn_msg = "WARNING", "RNNoise library not found — denoising will be skipped."
        else:
            frame = np.random.randn(160).astype(np.float32) * 0.01
            out = rn.denoise_frame(frame)
            rn.destroy()
            if out.dtype == np.float32:
                rn_status, rn_msg = "PASS", "RNNoise available and working."
            else:
                rn_status, rn_msg = "FAIL", f"RNNoise returned invalid dtype: {out.dtype}"
    except Exception as e:
        rn_status, rn_msg = "FAIL", f"RNNoise check error: {e}"

    if rn_status == "FAIL":
        overall_pass = False
        print_error(f"  - {rn_msg}")
    elif rn_status == "WARNING":
        print_warning(f"  - {rn_msg}")
    else:
        print_success(f"  - {rn_msg}")
    print(f"✓ RNNoise Check: {rn_status}")
    print("-" * 50)

    # 8. AGC Anti-Clipping Check
    print_info("Verifying AGC anti-clipping limiter...")
    try:
        agc = AutomaticGainControl()
        quiet = np.ones(480, dtype=np.float32) * 0.01
        agc.process(quiet)
        loud = np.ones(480, dtype=np.float32) * 0.9
        out = agc.process(loud)
        peak = float(np.max(np.abs(out)))
        clipping = int(np.sum(np.abs(out) > 1.0))
        if clipping > 0:
            agc_status, agc_msg = "FAIL", f"AGC produced {clipping} clipped samples (peak={peak:.4f})"
        else:
            agc_status, agc_msg = "PASS", f"AGC anti-clipping OK | peak={peak:.4f} (no clipping)"
    except Exception as e:
        agc_status, agc_msg = "FAIL", f"AGC check error: {e}"

    if agc_status == "FAIL":
        overall_pass = False
        print_error(f"  - {agc_msg}")
    else:
        print_success(f"  - {agc_msg}")
    print(f"✓ AGC Check: {agc_status}")
    print("-" * 50)

    # 9. Audio Diagnostics Check
    print_info("Verifying AudioDiagnostics metrics...")
    try:
        diag = AudioDiagnostics()
        t = np.linspace(0, 1.0, 16000, endpoint=False)
        sig = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        m = diag.measure(sig)
        required = ["rms", "peak", "noise_floor", "clipping_pct", "snr_db", "speech_dur_s"]
        missing  = [k for k in required if k not in m]
        if missing:
            diag_status, diag_msg = "FAIL", f"AudioDiagnostics missing keys: {missing}"
        else:
            diag_status, diag_msg = "PASS", f"rms={m['rms']:.4f} peak={m['peak']:.4f} snr={m['snr_db']:.1f}dB"
    except Exception as e:
        diag_status, diag_msg = "FAIL", f"AudioDiagnostics check error: {e}"

    if diag_status == "FAIL":
        overall_pass = False
        print_error(f"  - {diag_msg}")
    else:
        print_success(f"  - {diag_msg}")
    print(f"✓ AudioDiagnostics Check: {diag_status}")
    print("-" * 50)

    # 10. Speaker Verification Status
    print_info("Checking speaker verification enrollment...")
    try:
        verifier = SpeakerVerifier(
            embedding_path=speaker_embedding_path,
            threshold=speaker_similarity_threshold,
        )
        if not verifier.available:
            sv_status, sv_msg = "WARNING", "resemblyzer not installed — speaker verification disabled."
        elif not verifier.has_profile():
            sv_status, sv_msg = "WARNING", f"No speaker profile enrolled at '{speaker_embedding_path}'."
        else:
            meta = verifier.meta() or {}
            sv_status, sv_msg = "PASS", f"Enrolled embeddings: {verifier.total_embeddings} | Threshold: {speaker_similarity_threshold}"
    except Exception as e:
        sv_status, sv_msg = "FAIL", f"Speaker verification check error: {e}"

    if sv_status == "FAIL":
        overall_pass = False
        print_error(f"  - {sv_msg}")
    elif sv_status == "WARNING":
        print_warning(f"  - {sv_msg}")
    else:
        print_success(f"  - {sv_msg}")
    print(f"✓ Speaker Verification: {sv_status}")
    print("=" * 50)

    # Print final summary
    print(f"\n{COLOR_BOLD}=== FINAL SELF-TEST SUMMARY ==={COLOR_RESET}\n")
    print(f"  dependency check:          {'PASS' if dep_all_pass else 'FAIL'}")
    print(f"  microphone check:          {mic_status}")
    print(f"  model check:               {model_status}")
    print(f"  inference check:           {inf_status}")
    print(f"  wake-word signal:          {sig_status}")
    print(f"  STT check:                 {stt_status}")
    print(f"  RNNoise check:             {rn_status}")
    print(f"  AGC anti-clipping:         {agc_status}")
    print(f"  audio diagnostics:         {diag_status}")
    print(f"  speaker verification:      {sv_status}")
    print("\n" + "=" * 50)

    if overall_pass:
        print_success("OVERALL STATUS: PASS")
        sys.exit(0)
    else:
        print_error("OVERALL STATUS: FAIL")
        sys.exit(1)
