"""Unit tests for Step 6: Full-Duplex 16kHz PCM Audio Streaming."""

import pytest
import asyncio
import time
from nova.companion.streaming.audio_stream import CompanionAudioStreamer
from nova.companion.plugins.audio_plugin import AudioPlugin
from nova.companion.plugins.plugin_registry import PluginRegistry


def test_audio_plugin_registration():
    registry = PluginRegistry()
    plugin = AudioPlugin()
    registry.register_plugin(plugin)

    assert registry.get_plugin_for_action("audio.start_mic_stream") == plugin
    assert registry.get_plugin_for_action("audio.stop_mic_stream") == plugin
    assert registry.get_plugin_for_action("audio.play_tts_stream") == plugin


@pytest.mark.asyncio
async def test_audio_streamer_mic_and_tts_framing():
    streamer = CompanionAudioStreamer()

    # 1. Simulate Nova TTS synthesis output packing
    tts_pcm = b"\x00\x10\x00\x20\x00\x30" * 100  # 600 bytes PCM
    binary_tts_frame = streamer.pack_tts_speaker_frame(tts_pcm)
    assert len(binary_tts_frame) == 13 + len(tts_pcm)
    assert binary_tts_frame[0] == 0x0A

    # 2. Simulate phone mic binary frame processing
    seq, ts, pcm = streamer.process_incoming_mic_frame(binary_tts_frame)
    assert seq == 1
    assert pcm == tts_pcm

    # 3. Retrieve chunk for Whisper STT processing
    stt_chunk = await streamer.get_next_stt_audio_chunk(timeout=0.2)
    assert stt_chunk == tts_pcm

    streamer.stop()
