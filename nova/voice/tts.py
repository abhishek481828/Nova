import subprocess
import os
import asyncio
import tempfile
import threading
import numpy as np
from nova.voice.config import ENABLE_TTS, VOICE_NAME, TEMP_AUDIO_DIR, enable_debug
from nova.logger import logger
from nova.utils import print_info

# Thread-safe global interrupt accumulator & lock (High priority check)
_interrupt_accum = np.zeros(0, dtype=np.int16)
_interrupt_lock = threading.Lock()

def reset_interrupt_accumulator() -> None:
    """Safely reset the interrupt detection accumulator."""
    global _interrupt_accum
    with _interrupt_lock:
        _interrupt_accum = np.zeros(0, dtype=np.int16)


def check_for_wake_interrupt() -> bool:
    global _interrupt_accum
    import nova.voice.config as voice_config

    stream = voice_config.active_stream
    detector = voice_config.active_wake_detector
    if not stream or not detector:
        return False

    try:
        with voice_config.stream_lock:
            available = stream.read_available
            if available >= 480:
                chunks_to_read = available // 480
                for _ in range(chunks_to_read):
                    recording, _ = stream.read(480)
                    flat = recording.flatten()

                    # Apply Acoustic Echo Cancellation if enabled
                    aec = getattr(voice_config, "active_aec", None)
                    if aec is not None:
                        flat = aec.process(flat)

                    # Apply gain and convert to PCM int16 for OpenWakeWord
                    amplified = flat * 2.0
                    pcm_chunk = (np.clip(amplified, -1.0, 1.0) * 32767).astype(np.int16)

                    with _interrupt_lock:
                        _interrupt_accum = np.concatenate((_interrupt_accum, pcm_chunk))

            # Thread-safe check of the accumulator and run OWW predict
            frame = None
            with _interrupt_lock:
                if len(_interrupt_accum) >= 1280:
                    frame = _interrupt_accum[:1280]
                    _interrupt_accum = _interrupt_accum[1280:]

            if frame is not None:
                # OWW model is locked internally in WrappedPredict
                predictions = detector.model.predict(frame)
                score = predictions.get(detector.model_name, 0.0)

                # Use higher threshold to prevent self-interruption from speech echo
                if score >= 0.12:
                    return True
    except Exception:
        pass
    return False

class TextToSpeechProvider:
    def speak(self, text: str) -> None:
        raise NotImplementedError()


class EdgeTTSProvider(TextToSpeechProvider):
    def __init__(self, voice: str = VOICE_NAME):
        self.voice = voice

    def _synthesize(self, text: str) -> str:
        """Download TTS audio to a temp mp3 file, return its path."""
        import edge_tts

        async def _amain() -> str:
            communicate = edge_tts.Communicate(text, self.voice, rate="-3%")
            temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3", dir=TEMP_AUDIO_DIR)
            os.close(temp_fd)
            await communicate.save(temp_path)
            return temp_path

        try:
            asyncio.get_running_loop()
            loop_is_running = True
        except RuntimeError:
            loop_is_running = False

        if loop_is_running:
            import threading
            result = [None]
            def _run():
                new_loop = asyncio.new_event_loop()
                try:
                    result[0] = new_loop.run_until_complete(_amain())
                finally:
                    new_loop.close()
            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=15)
            return result[0]
        else:
            return asyncio.run(_amain())

    def _play(self, mp3_path: str) -> None:
        """
        Play an mp3 file using the first working audio backend.
        Tries: sounddevice (numpy decode) → mpg123 -o alsa → ffplay.
        Never uses JACK so it works under PipeWire without a JACK server.
        """
        import nova.voice.config as voice_config
        import numpy as np
        import time

        # Load playback reference audio for AEC
        try:
            import soundfile as sf
            ref_data, ref_rate = sf.read(mp3_path, dtype='float32')
            if len(ref_data.shape) > 1 and ref_data.shape[1] > 1:
                ref_data = np.mean(ref_data, axis=1)
            # Resample to 16000 Hz if needed
            if ref_rate != 16000:
                try:
                    from scipy.signal import resample_poly
                except ImportError:
                    resample_poly = None

                if resample_poly is not None:
                    ref_data = resample_poly(ref_data, up=16000, down=ref_rate)
                else:
                    xp = np.arange(len(ref_data))
                    x = np.linspace(0, len(ref_data) - 1, int(len(ref_data) * 16000 / ref_rate))
                    ref_data = np.interp(x, xp, ref_data).astype(np.float32)
            voice_config.aec_reference_audio = ref_data
            voice_config.aec_playback_start_time = time.time()
        except Exception as ref_err:
            logger.debug(f"AEC reference audio load failed: {ref_err}")
            voice_config.aec_reference_audio = None
            voice_config.aec_playback_start_time = None

        # Reset wake-word detector accumulator for this playback turn
        reset_interrupt_accumulator()

        try:
            # 1. sounddevice + soundfile (no external binary, best latency)
            try:
                import soundfile as sf
                import sounddevice as sd
                data, rate = sf.read(mp3_path, dtype='float32')
                sd.play(data, rate)
                
                # Periodically poll for interrupt signal or wake word
                while sd.get_stream().active:
                    if voice_config.interrupt_speaking or check_for_wake_interrupt():
                        sd.stop()
                        voice_config.interrupt_speaking = True
                        break
                    time.sleep(0.05)
                return
            except Exception as e:
                logger.debug(f"sounddevice playback failed: {e}")

            # 2. mpg123 with explicit ALSA output (works under PipeWire)
            try:
                proc = subprocess.Popen(
                    ["mpg123", "-o", "alsa", "-q", mp3_path],
                    stderr=subprocess.DEVNULL,
                )
                while proc.poll() is None:
                    if voice_config.interrupt_speaking or check_for_wake_interrupt():
                        proc.terminate()
                        proc.wait()
                        voice_config.interrupt_speaking = True
                        break
                    time.sleep(0.05)
                return
            except Exception as e:
                logger.debug(f"mpg123 -o alsa playback failed: {e}")

            # 3. ffplay (ffmpeg suite, no window, quiet)
            try:
                proc = subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", mp3_path],
                    stderr=subprocess.DEVNULL,
                )
                while proc.poll() is None:
                    if voice_config.interrupt_speaking or check_for_wake_interrupt():
                        proc.terminate()
                        proc.wait()
                        voice_config.interrupt_speaking = True
                        break
                    time.sleep(0.05)
                return
            except Exception as e:
                logger.debug(f"ffplay playback failed: {e}")
        finally:
            # Let reference audio remain available for AEC in the subsequent record loop (High priority fix)
            pass

        logger.debug("All TTS playback backends failed — audio not played.")

    def speak(self, text: str) -> None:
        if not ENABLE_TTS or not text.strip():
            return

        import edge_tts
        import time
        import numpy as np
        import io
        import soundfile as sf
        import nova.voice.config as voice_config

        if enable_debug:
            print_info("🔊 Speaking (streaming)...")

        async def _stream_and_play():
            communicate = edge_tts.Communicate(text, self.voice, rate="-3%")
            
            # Spawn mpg123 reading from stdin
            proc = None
            try:
                proc = subprocess.Popen(
                    ["mpg123", "-q", "-"],
                    stdin=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                logger.debug(f"Failed to start mpg123 stdin player: {e}")
                
            # Accumulate MP3 bytes in memory for AEC decoding
            mp3_io = io.BytesIO()
            
            # Reset wake-word detector accumulator for this playback turn
            reset_interrupt_accumulator()
                
            # Set AEC start time
            voice_config.aec_playback_start_time = time.time()
            
            try:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_bytes = chunk["data"]
                        # Pipe to mpg123
                        if proc and proc.poll() is None:
                            try:
                                proc.stdin.write(audio_bytes)
                                proc.stdin.flush()
                            except Exception:
                                pass
                        # Accumulate for AEC
                        mp3_io.write(audio_bytes)
                        
                    # Check for interrupt
                    if voice_config.interrupt_speaking or check_for_wake_interrupt():
                        voice_config.interrupt_speaking = True
                        break
                        
                # Close stdin to let mpg123 finish playing
                if proc and proc.stdin:
                    proc.stdin.close()
                    
                # Wait for mpg123 to finish (unless interrupted)
                if proc:
                    while proc.poll() is None:
                        if voice_config.interrupt_speaking or check_for_wake_interrupt():
                            proc.terminate()
                            proc.wait()
                            voice_config.interrupt_speaking = True
                            break
                        await asyncio.sleep(0.05)
                        
            finally:
                if proc and proc.poll() is None:
                    proc.terminate()
                    proc.wait()
                    
            # Decode the accumulated MP3 bytes in memory for AEC reference
            try:
                mp3_io.seek(0)
                if mp3_io.getbuffer().nbytes > 0:
                    ref_data, ref_rate = sf.read(mp3_io, dtype='float32')
                    if len(ref_data.shape) > 1 and ref_data.shape[1] > 1:
                        ref_data = np.mean(ref_data, axis=1)
                    if ref_rate != 16000:
                        try:
                            from scipy.signal import resample_poly
                        except ImportError:
                            resample_poly = None
                        if resample_poly is not None:
                            ref_data = resample_poly(ref_data, up=16000, down=ref_rate)
                        else:
                            xp = np.arange(len(ref_data))
                            x = np.linspace(0, len(ref_data) - 1, int(len(ref_data) * 16000 / ref_rate))
                            ref_data = np.interp(x, xp, ref_data).astype(np.float32)
                    voice_config.aec_reference_audio = ref_data
            except Exception as aec_err:
                logger.debug(f"Streaming AEC reference decode failed: {aec_err}")

        try:
            # Check if there is an active event loop
            try:
                loop = asyncio.get_running_loop()
                loop_is_running = True
            except RuntimeError:
                loop_is_running = False

            if loop_is_running:
                import threading
                def _run():
                    new_loop = asyncio.new_event_loop()
                    try:
                        new_loop.run_until_complete(_stream_and_play())
                    finally:
                        new_loop.close()
                t = threading.Thread(target=_run, daemon=True)
                t.start()
                t.join(timeout=30)
            else:
                asyncio.run(_stream_and_play())
        except Exception as e:
            logger.debug(f"Streaming speak failed: {e}")
        finally:
            # Let reference audio remain available for AEC in the subsequent record loop (High priority fix)
            pass


class ElevenLabsProvider(TextToSpeechProvider):
    """
    TTS provider using ElevenLabs API (Bella voice).
    Falls back gracefully to EdgeTTSProvider if API key is not configured,
    or if ElevenLabs service is temporarily unavailable.
    """
    def __init__(self):
        # Load dotenv to read .env keys into environment variables
        try:
            from dotenv import load_dotenv
            from pathlib import Path
            load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env", override=True)
        except ImportError:
            pass
        self.api_key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY")
        self.voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
        self.fallback = EdgeTTSProvider()

    def speak(self, text: str) -> None:
        if not ENABLE_TTS or not text.strip():
            return

        if not self.api_key:
            logger.debug("ElevenLabs API key not found. Falling back to Edge TTS.")
            self.fallback.speak(text)
            return

        if enable_debug:
            print_info("🔊 Speaking with ElevenLabs...")
        
        import tempfile
        from elevenlabs.client import ElevenLabs
        from elevenlabs import VoiceSettings
        
        _voice_settings = VoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
            style=0.0,
            use_speaker_boost=True,
            speed=0.95,
        )
        
        mp3_path = None
        try:
            client = ElevenLabs(api_key=self.api_key)
            
            # Attempt to use the user-configured Voice ID
            try:
                audio = client.text_to_speech.convert(
                    text=text,
                    voice_id=self.voice_id,
                    model_id="eleven_turbo_v2_5",
                    output_format="mp3_44100_128",
                    voice_settings=_voice_settings,
                )
                chunks = list(audio)
            except Exception as e:
                # If custom voice ID fails (e.g., 402 payment required on free tier)
                # and it's different from default Bella, try default Bella voice ID
                if self.voice_id != "EXAVITQu4vr4xnSDxMaL":
                    logger.debug(f"ElevenLabs custom voice {self.voice_id} failed: {e}. Trying default Bella voice.")
                    audio = client.text_to_speech.convert(
                        text=text,
                        voice_id="EXAVITQu4vr4xnSDxMaL",
                        model_id="eleven_turbo_v2_5",
                        output_format="mp3_44100_128",
                        voice_settings=_voice_settings,
                    )
                    chunks = list(audio)
                else:
                    raise e
            
            temp_fd, mp3_path = tempfile.mkstemp(suffix=".mp3", dir=TEMP_AUDIO_DIR)
            os.close(temp_fd)
            
            with open(mp3_path, "wb") as f:
                for chunk in chunks:
                    f.write(chunk)
                    
            self.fallback._play(mp3_path)
        except Exception as e:
            logger.debug(f"ElevenLabs TTS failed: {e}. Falling back to Edge TTS.")
            self.fallback.speak(text)
        finally:
            if mp3_path and os.path.exists(mp3_path):
                try:
                    os.remove(mp3_path)
                except Exception:
                    pass


class OpenAITTSProvider(TextToSpeechProvider):
    """
    TTS provider using OpenAI's TTS API.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.voice = os.environ.get("OPENAI_TTS_VOICE", "nova")
        self.fallback = EdgeTTSProvider()
        self.client = None

    def speak(self, text: str) -> None:
        if not ENABLE_TTS or not text.strip():
            return

        import httpx
        import tempfile

        if enable_debug:
            print_info(f"🔊 Speaking with OpenAI TTS ({self.voice})...")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        url = "https://api.openai.com/v1/audio/speech"
        payload = {
            "model": "tts-1",
            "input": text,
            "voice": self.voice
        }

        if self.client is None:
            self.client = httpx.Client(timeout=15.0)

        mp3_path = None
        try:
            response = self.client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            audio_bytes = response.content

            temp_fd, mp3_path = tempfile.mkstemp(suffix=".mp3", dir=TEMP_AUDIO_DIR)
            os.close(temp_fd)

            with open(mp3_path, "wb") as f:
                f.write(audio_bytes)

            self.fallback._play(mp3_path)
        except Exception as e:
            logger.debug(f"OpenAI TTS failed: {e}. Falling back to Edge TTS.")
            self.fallback.speak(text)
        finally:
            if mp3_path and os.path.exists(mp3_path):
                try:
                    os.remove(mp3_path)
                except Exception:
                    pass


class DeepgramTTSProvider(TextToSpeechProvider):
    """
    TTS provider using Deepgram's Speak API (Aura models).
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.voice = os.environ.get("DEEPGRAM_TTS_VOICE", "aura-asteria-en")
        self.fallback = EdgeTTSProvider()
        self.client = None

    def speak(self, text: str) -> None:
        if not ENABLE_TTS or not text.strip():
            return

        import httpx
        import tempfile

        if enable_debug:
            print_info(f"🔊 Speaking with Deepgram TTS ({self.voice})...")

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json"
        }
        url = f"https://api.deepgram.com/v1/speak?model={self.voice}"
        payload = {"text": text}

        if self.client is None:
            self.client = httpx.Client(timeout=15.0)

        mp3_path = None
        try:
            response = self.client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            audio_bytes = response.content

            temp_fd, mp3_path = tempfile.mkstemp(suffix=".mp3", dir=TEMP_AUDIO_DIR)
            os.close(temp_fd)

            with open(mp3_path, "wb") as f:
                f.write(audio_bytes)

            self.fallback._play(mp3_path)
        except Exception as e:
            logger.debug(f"Deepgram TTS failed: {e}. Falling back to Edge TTS.")
            self.fallback.speak(text)
        finally:
            if mp3_path and os.path.exists(mp3_path):
                try:
                    os.remove(mp3_path)
                except Exception:
                    pass


# Lazily initialized provider
_tts_provider: TextToSpeechProvider | None = None


def speak(text: str) -> None:
    import nova.voice.config as voice_config
    voice_config.interrupt_speaking = False
    global _tts_provider
    if _tts_provider is None:
        deepgram_key = os.environ.get("DEEPGRAM_API_KEY")
        eleven_key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")

        if deepgram_key:
            _tts_provider = DeepgramTTSProvider(api_key=deepgram_key)
        elif eleven_key:
            _tts_provider = ElevenLabsProvider()
        elif openai_key:
            _tts_provider = OpenAITTSProvider(api_key=openai_key)
        else:
            _tts_provider = EdgeTTSProvider()
    print(f"🔊 {text}")
    
    # Emit to Dashboard
    try:
        from nova.dashboard.event_bus import emit
        emit("tts_started", module="tts", status="running", metadata={"text": text})
    except Exception:
        pass

    try:
        _tts_provider.speak(text)
        
        # Emit to Dashboard
        try:
            from nova.dashboard.event_bus import emit
            emit("tts_finished", module="tts", status="success", metadata={"text": text})
        except Exception:
            pass
    except Exception as e:
        # Emit Failed status to Dashboard
        try:
            from nova.dashboard.event_bus import emit
            emit("tts_finished", module="tts", status="failed", metadata={"text": text, "error": str(e)})
        except Exception:
            pass
        raise e
