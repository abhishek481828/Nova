"""Low-Latency 16kHz PCM Full-Duplex Audio Streamer for Nova v2.0."""

import asyncio
import logging
import time
from typing import Optional, Tuple
from nova.companion.protocol.framing import (
    create_binary_audio_frame,
    unpack_binary_audio_frame,
    BINARY_FRAME_AUDIO
)

logger = logging.getLogger("nova.companion.streaming.audio")


class CompanionAudioStreamer:
    """Manages audio buffer streams between Companion phone mic/speaker and Nova Voice Pipeline."""

    SAMPLE_RATE = 16000
    CHANNELS = 1
    BYTES_PER_SAMPLE = 2  # 16-bit PCM

    def __init__(self):
        self._is_streaming = False
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._seq_num = 0

    def process_incoming_mic_frame(self, raw_bytes: bytes) -> Optional[Tuple[int, int, bytes]]:
        """Unpacks binary audio frame from phone microphone."""
        try:
            seq_num, ts_ms, pcm_data = unpack_binary_audio_frame(raw_bytes)
            if not self._is_streaming:
                self._is_streaming = True
            self._audio_queue.put_nowait((seq_num, ts_ms, pcm_data))
            return seq_num, ts_ms, pcm_data
        except Exception as e:
            logger.error(f"Error unpacking incoming mic frame: {e}")
            return None

    async def get_next_stt_audio_chunk(self, timeout: float = 0.5) -> Optional[bytes]:
        """Retrieves next 16kHz PCM audio chunk for Whisper STT processing."""
        try:
            _, _, pcm_bytes = await asyncio.wait_for(self._audio_queue.get(), timeout=timeout)
            return pcm_bytes
        except asyncio.TimeoutError:
            return None

    def pack_tts_speaker_frame(self, tts_pcm_bytes: bytes) -> bytes:
        """Packs synthesized TTS audio bytes into binary frame for phone speaker playback."""
        self._seq_num += 1
        ts_ms = int(time.time() * 1000)
        return create_binary_audio_frame(self._seq_num, ts_ms, tts_pcm_bytes)

    def stop(self):
        self._is_streaming = False
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()
