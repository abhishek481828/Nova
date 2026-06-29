import os
import time
from nova.voice.config import (
    NEBIUS_STT_URL, NEBIUS_MODEL_NAME, API_TIMEOUT, RETRY_COUNT,
    WHISPER_MODEL_SIZE, WHISPER_CPU_THREADS, WHISPER_NUM_WORKERS, WHISPER_BEAM_SIZE,
    enable_debug,
)
from nova.logger import logger
from nova.utils import print_info, print_warning, print_error


class SpeechToTextProvider:
    def transcribe(self, audio: "str | bytes", silent: bool = False) -> str:
        raise NotImplementedError()


class WhisperSTTProvider(SpeechToTextProvider):
    _cached_model = None
    """
    Fully offline local STT using faster-whisper.
    Model sizes: tiny (~75MB fastest), base (~145MB), small (~470MB), medium (~1.5GB)
    Configure size and parameters in voice/config.py.
    """

    def __init__(self, model_size: "str | None" = None):
        self.model_size = model_size or WHISPER_MODEL_SIZE

    def _load(self):
        if WhisperSTTProvider._cached_model is not None:
            return
        try:
            from faster_whisper import WhisperModel
            if enable_debug:
                print_info(f"🔄 Loading local Whisper '{self.model_size}' model (first run only)...")
            WhisperSTTProvider._cached_model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
                cpu_threads=WHISPER_CPU_THREADS,
                num_workers=WHISPER_NUM_WORKERS,
            )
            if enable_debug:
                print_info("✅ Local Whisper model ready.")
        except Exception as e:
            raise RuntimeError(f"Failed to load Whisper model '{self.model_size}': {e}")

    def transcribe(self, audio: "str | bytes", silent: bool = False) -> str:
        self._load()
        import tempfile, wave, struct, numpy as np

        if not silent or enable_debug:
            if enable_debug:
                print_info("🧠 Transcribing locally with Whisper...")

        # faster-whisper needs a file path, not bytes
        if isinstance(audio, str):
            audio_path = audio
            cleanup = False
        else:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(audio)
            tmp.close()
            audio_path = tmp.name
            cleanup = True

        try:
            # Energy gate: if the audio is essentially silence, Whisper will
            # hallucinate random text. Abort early if RMS < threshold.
            try:
                with wave.open(audio_path, 'rb') as wf:
                    raw = wf.readframes(wf.getnframes())
                    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) > 0 else 0.0
                if rms < 0.01:
                    logger.debug(f"Audio energy too low ({rms:.4f}) — skipping transcription.")
                    return ""
            except Exception:
                pass  # if we can't check energy, proceed anyway

            segments, _ = WhisperSTTProvider._cached_model.transcribe(
                audio_path,
                language="en",
                beam_size=WHISPER_BEAM_SIZE,
                vad_filter=True,           # strips silence so Whisper doesn't hallucinate
                vad_parameters={"min_silence_duration_ms": 300},
                # Bias Whisper toward Nova command vocabulary and patterns.
                # This dramatically reduces hallucinations on short utterances.
                initial_prompt=(
                    "Hey Nova. Open Chromium. Open Chrome. Open Firefox. Open VS Code. "
                    "Open Visual Studio Code. Open the terminal. Open Spotify. Open Discord. "
                    "Open ChatGPT. Open GitHub. Open Google. Open YouTube. Open Gmail. Open Reddit. "
                    "Play Love Me Like You Do by Ellie Goulding. "
                    "Play Sweater Weather. Play Believer. Play Perfect by Ed Sheeran. "
                    "Play Shape of You. Play Arijit Singh. Play Taylor Swift. Play Justin Bieber. "
                    "Bitcoin. Ethereum. Linux. NixOS. Python. Docker. Kubernetes. "
                    "Set brightness to 50 percent. Set volume to 80. Connect to WiFi. "
                    "Install package. Uninstall package. Update system. Close browser. "
                    "Do you remember my name? Tell me a joke."
                ),
            )
            segments_list = list(segments)
            if segments_list:
                self.last_avg_logprob = sum(seg.avg_logprob for seg in segments_list) / len(segments_list)
            else:
                self.last_avg_logprob = 0.0

            return " ".join(seg.text for seg in segments_list).strip()
        except Exception as e:
            raise Exception(f"Whisper transcription error: {e}")
        finally:
            if cleanup:
                try:
                    os.unlink(audio_path)
                except Exception:
                    pass


class NebiusSTTProvider(SpeechToTextProvider):
    """
    Remote STT via Nebius API (OpenAI-compatible endpoint).
    NOTE: Nebius does not currently host a Whisper/audio endpoint — this will
    return 404 unless you have a custom deployment. Use WhisperSTTProvider instead.
    """

    def __init__(
        self,
        api_key: str,
        url: str = NEBIUS_STT_URL,
        model: str = NEBIUS_MODEL_NAME,
        timeout: float = API_TIMEOUT,
        max_retries: int = RETRY_COUNT,
    ):
        self.api_key = api_key
        self.url = url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def transcribe(self, audio: "str | bytes", silent: bool = False) -> str:
        if not self.api_key:
            raise ValueError("Nebius API key is missing.")

        import httpx

        if isinstance(audio, str):
            try:
                with open(audio, "rb") as f:
                    audio_bytes = f.read()
            except Exception as e:
                raise Exception(f"Failed to read WAV file {audio}: {e}")
        else:
            audio_bytes = audio

        if not silent:
            print_info("📤 Uploading audio...")
            print_info("🧠 Transcribing via Nebius...")

        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {"model": self.model}
        files = {"file": ("audio.wav", audio_bytes, "audio/wav")}

        backoff = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(self.url, headers=headers, data=data, files=files)
                    response.raise_for_status()
                    return response.json().get("text", "").strip()

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403, 404):
                    raise Exception(f"Nebius API client error {status_code}: {e.response.text}")
                if status_code >= 500:
                    if attempt == self.max_retries:
                        raise Exception(
                            f"Nebius API server error {status_code} after {self.max_retries} retries: {e.response.text}"
                        )
                    logger.debug(f"Nebius STT attempt {attempt} failed ({status_code}). Retry in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2.0
                else:
                    raise Exception(f"Nebius API error {status_code}: {e.response.text}")

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt == self.max_retries:
                    raise Exception(f"Nebius API network error: {e} (after {self.max_retries} retries)")
                logger.debug(f"Nebius STT attempt {attempt} network error: {e}. Retry in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2.0
            except Exception as e:
                raise Exception(f"Unexpected STT error: {e}")

        return ""


class OpenAISTTProvider(SpeechToTextProvider):
    """
    Remote STT via OpenAI's Whisper API.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key

    def transcribe(self, audio: "str | bytes", silent: bool = False) -> str:
        if not self.api_key:
            raise ValueError("OpenAI API key is missing.")

        import httpx

        if isinstance(audio, str):
            try:
                with open(audio, "rb") as f:
                    audio_bytes = f.read()
            except Exception as e:
                raise Exception(f"Failed to read WAV file {audio}: {e}")
        else:
            audio_bytes = audio

        if not silent:
            print_info("🧠 Transcribing via OpenAI Whisper API...")

        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = "https://api.openai.com/v1/audio/transcriptions"
        data = {"model": "whisper-1", "language": "en"}
        files = {"file": ("audio.wav", audio_bytes, "audio/wav")}

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(url, headers=headers, data=data, files=files)
                response.raise_for_status()
                return response.json().get("text", "").strip()
        except Exception as e:
            raise Exception(f"OpenAI Whisper API error: {e}")


class GroqSTTProvider(SpeechToTextProvider):
    """
    Remote STT via Groq's Whisper API.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key

    def transcribe(self, audio: "str | bytes", silent: bool = False) -> str:
        if not self.api_key:
            raise ValueError("Groq API key is missing.")

        import httpx

        if isinstance(audio, str):
            try:
                with open(audio, "rb") as f:
                    audio_bytes = f.read()
            except Exception as e:
                raise Exception(f"Failed to read WAV file {audio}: {e}")
        else:
            audio_bytes = audio

        if not silent:
            print_info("🧠 Transcribing via Groq Whisper API...")

        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        data = {"model": "whisper-large-v3", "language": "en"}
        files = {"file": ("audio.wav", audio_bytes, "audio/wav")}

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(url, headers=headers, data=data, files=files)
                response.raise_for_status()
                return response.json().get("text", "").strip()
        except Exception as e:
            raise Exception(f"Groq Whisper API error: {e}")


class DeepgramSTTProvider(SpeechToTextProvider):
    """
    Remote STT via Deepgram's Listen API.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key

    def transcribe(self, audio: "str | bytes", silent: bool = False) -> str:
        if not self.api_key:
            raise ValueError("Deepgram API key is missing.")

        import httpx

        if isinstance(audio, str):
            try:
                with open(audio, "rb") as f:
                    audio_bytes = f.read()
            except Exception as e:
                raise Exception(f"Failed to read WAV file {audio}: {e}")
        else:
            audio_bytes = audio

        if not silent:
            print_info("🧠 Transcribing via Deepgram Nova-2 API...")

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/wav"
        }
        url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true"

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(url, headers=headers, content=audio_bytes)
                response.raise_for_status()
                resp_json = response.json()
                
                channels = resp_json.get("results", {}).get("channels", [])
                if channels:
                    alternatives = channels[0].get("alternatives", [])
                    if alternatives:
                        return alternatives[0].get("transcript", "").strip()
                return ""
        except Exception as e:
            raise Exception(f"Deepgram STT API error: {e}")


def get_stt_provider() -> SpeechToTextProvider:
    """
    Returns the best available STT provider based on configured API keys.

    Priority:
      1. Deepgram (if DEEPGRAM_API_KEY is present)
      2. Groq (if GROQ_API_KEY is present)
      3. OpenAI (if OPENAI_API_KEY is present)
      4. Nebius remote (if forced via NOVA_STT_PROVIDER=nebius)
      5. Local faster-whisper (offline fallback)
    """
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY")
    if deepgram_key:
        return DeepgramSTTProvider(api_key=deepgram_key)

    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        return GroqSTTProvider(api_key=groq_key)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        return OpenAISTTProvider(api_key=openai_key)

    forced = os.environ.get("NOVA_STT_PROVIDER", "").lower()
    if forced == "nebius":
        api_key = os.environ.get("NEBIUS_API_KEY", "")
        return NebiusSTTProvider(api_key=api_key)

    return WhisperSTTProvider()
