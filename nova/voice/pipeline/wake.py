import time
import collections
import numpy as np
import sounddevice as sd
from nova.logger import logger
import nova.voice.config as voice_config
from nova.voice.config import SAMPLE_RATE, enable_debug
from nova.voice.pipeline.recorder import CircularAudioBuffer
from nova.voice.pipeline.state_machine import (
    VoiceState,
    voice_active_event,
    shutdown_event,
    get_current_state,
    recover_microphone,
)
from nova.voice.media_control import duck_all_media, unduck_players

_WAKE_CHUNK = 480
_WAKE_FRAME = 1280
_WAKE_CAPTURE_SECS = 2.0

def _wait_for_wake(
    stream: sd.InputStream,
    wake_detector,
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
    _DETECT_THRESHOLD = 0.04
    _PATIENCE = 1
    _PATIENCE_WINDOW = 2
    score_history = collections.deque(maxlen=_PATIENCE_WINDOW)
    last_trigger = 0.0
    _WARMUP_FRAMES = 6
    warmup_remaining = _WARMUP_FRAMES

    # Duck media volume so "Hey Nova" can be heard over background audio
    _ducked_volumes: dict = {}
    try:
        _ducked_volumes = duck_all_media()
    except Exception as _e:
        logger.debug(f"Media duck failed: {_e}")

    while True:
        current_state = get_current_state()
        if shutdown_event.is_set() or current_state == VoiceState.INACTIVE:
            unduck_players(_ducked_volumes)
            return False, None, 0.0
        if voice_active_event.is_set():
            voice_active_event.clear()
            unduck_players(_ducked_volumes)
            return True, None, 1.0

        try:
            with voice_config.stream_lock:
                recording, _ = stream.read(_WAKE_CHUNK)
        except Exception as e:
            logger.debug(f"Wake-loop read error: {e}")
            stream = recover_microphone(stream)
            current_state = get_current_state()
            if shutdown_event.is_set() or current_state == VoiceState.INACTIVE:
                return False, None, 0.0
            continue

        flat = recording.flatten()
        aec = getattr(voice_config, "active_aec", None)
        if aec is not None:
            flat = aec.process(flat)
        capture_buffer.extend(flat)

        # Apply RMS normalization with a safety gain limit to match diag_wake.py behavior
        rms = float(np.sqrt(np.mean(flat * flat)))
        TARGET_RMS = 0.08
        if rms > 1e-6:
            gain = min(8.0, TARGET_RMS / rms)
            normalized = flat * gain
        else:
            normalized = flat * _SOFTWARE_GAIN

        pcm_chunk = (np.clip(normalized, -1.0, 1.0) * 32767).astype(np.int16)
        oww_accum = np.concatenate((oww_accum, pcm_chunk))


        if len(oww_accum) < _WAKE_FRAME:
            continue

        oww_frame = oww_accum[:_WAKE_FRAME]
        oww_accum = oww_accum[_WAKE_FRAME // 2:]  # 50% overlap — matches diag_wake.py behavior

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
            # Restore volume before returning — core.py will do a full pause next
            unduck_players(_ducked_volumes)
            return True, wake_audio, float(score)
