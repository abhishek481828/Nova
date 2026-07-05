import io
import time
import wave
import numpy as np

import nova.voice.config as voice_config
from nova.voice.config import (
    SAMPLE_RATE, CHANNELS, RECORDING_TIMEOUT, SILENCE_TIMEOUT,
    VAD_THRESHOLD, HIGHPASS_CUTOFF, VAD_AGGRESSIVENESS,
    ENABLE_NOISE_SUPPRESSION, ENABLE_HIGHPASS_FILTER, ENABLE_AGC, ENABLE_VAD,
    ENABLE_DC_OFFSET_REMOVAL, BLOCK_SIZE,
    VAD_PRE_PADDING_FRAMES, VAD_POST_PADDING_FRAMES, enable_debug,
)
from nova.logger import logger
from nova.utils import print_info, print_warning
from nova.voice.pipeline.processors import (
    RNNoiseWrapper,
    HighPassFilter,
    AutomaticGainControl,
    WebRTCVoiceActivityDetector,
    AecProcessor,
)

def calculate_rms(audio_chunk: np.ndarray) -> float:
    if len(audio_chunk) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio_chunk))))


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
                    is_settled = len(audio_data) >= 10
                    if last_is_speech and is_settled:
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
    from nova.voice.pipeline.state_machine import get_current_state, VoiceState, shutdown_event
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

            # Settling period (10 frames = ~300ms) to prevent trailing speaker echoes/clicks from causing premature silence cutoffs
            is_settled = len(audio_data) >= 10

            if is_speech and is_settled:
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
