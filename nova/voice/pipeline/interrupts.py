import re
import io
import time
import wave
import threading
import numpy as np
from nova.logger import logger
from nova.voice.config import SAMPLE_RATE
import nova.voice.config as voice_config

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
        import sounddevice as sd
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
    from nova.voice.tts import speak
    from nova.voice.pipeline.recorder import record_audio_from_stream
    from nova.voice.whisper import get_stt_provider
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
