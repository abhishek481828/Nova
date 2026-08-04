import pytest
import asyncio
import base64
import json
from unittest.mock import MagicMock, AsyncMock, patch

from nova.actions.audio_voice import (
    AudioCaptureStartAction,
    AudioCaptureStopAction,
    VoiceSessionStartAction,
    VoiceSessionStopAction,
    AudioPlayAction,
    AudioStopAction,
    MicrophoneMuteAction,
    MicrophoneUnmuteAction,
    SpeakerVolumeSetAction,
    SpeakerVolumeGetAction,
)
from nova.companion.audio_receiver import AudioReceiver


def test_audio_capture_actions():
    start_action = AudioCaptureStartAction()
    stop_action = AudioCaptureStopAction()
    
    with patch("nova.actions.audio_voice.send_companion_command", return_value={"status": "success", "data": {"packets_sent": 100, "total_bytes": 64000}}):
        res1 = start_action.execute({})
        assert "Successfully started remote audio capture" in res1
        
        res2 = stop_action.execute({})
        assert "Successfully stopped" in res2


def test_voice_session_actions():
    start_action = VoiceSessionStartAction()
    stop_action = VoiceSessionStopAction()
    
    with patch("nova.actions.audio_voice.send_companion_command", return_value={"status": "success", "data": {"session_id": "vsess_99", "duration_seconds": 12, "packets_transmitted": 500}}):
        res1 = start_action.execute({})
        assert "Successfully started voice session" in res1
        
        res2 = stop_action.execute({})
        assert "Successfully stopped voice session" in res2


def test_audio_play_and_stop_actions():
    play_action = AudioPlayAction()
    stop_action = AudioStopAction()
    raw_pcm = b"\x00\x01\x02\x03" * 100
    b64_audio = base64.b64encode(raw_pcm).decode("utf-8")
    
    with patch("nova.actions.audio_voice.send_companion_command", return_value={"status": "success"}):
        res1 = play_action.execute({"audio_data": b64_audio, "sample_rate": 16000})
        assert "Successfully playing synthesized speech audio" in res1
        
        res2 = stop_action.execute({})
        assert "Successfully stopped audio playback" in res2


def test_microphone_mute_unmute_actions():
    mute_action = MicrophoneMuteAction()
    unmute_action = MicrophoneUnmuteAction()
    
    with patch("nova.actions.audio_voice.send_companion_command", return_value={"status": "success"}):
        res1 = mute_action.execute({})
        assert "Successfully muted phone microphone" in res1
        
        res2 = unmute_action.execute({})
        assert "Successfully unmuted phone microphone" in res2


def test_speaker_volume_actions():
    set_action = SpeakerVolumeSetAction()
    get_action = SpeakerVolumeGetAction()
    
    with patch("nova.actions.audio_voice.send_companion_command", return_value={"status": "success", "data": {"volume_percent": 80, "current_level": 12, "max_level": 15}}):
        res1 = set_action.execute({"level": 80})
        assert "Successfully set phone speaker volume to 80%" in res1
        
        res2 = get_action.execute({})
        assert "Phone Speaker Volume: 80%" in res2


@pytest.mark.asyncio
async def test_audio_receiver_pcm_processing():
    receiver = AudioReceiver()
    receiver.start_session("session_abc")
    assert receiver.is_active is True

    # Process 3 sequential frames
    for seq in range(1, 4):
        pcm_bytes = f"pcm_chunk_{seq}".encode("utf-8").ljust(640, b"\x00")
        header = {"seq": seq, "timestamp": 1000 + seq}
        res = receiver.process_pcm_packet(header, pcm_bytes)
        assert res["status"] == "packet_processed"
        assert res["seq"] == seq

    assert receiver.total_packets_received == 3
    assert receiver.dropped_packets == 0
    assert receiver.last_sequence == 3
    assert len(receiver.buffer) == 640 * 3

    # Test out of sequence frame (dropped packet detection: seq 6 when last was 3 -> 2 dropped: 4, 5)
    out_of_seq_pcm = b"out_of_seq".ljust(640, b"\x00")
    header = {"seq": 6, "timestamp": 1010}
    receiver.process_pcm_packet(header, out_of_seq_pcm)
    
    assert receiver.total_packets_received == 4
    assert receiver.dropped_packets == 2

    # Verify audio data extraction for STT
    audio_data = receiver.get_stt_audio_data()
    assert len(audio_data) == 640 * 4
    assert len(receiver.buffer) == 0

    stop_res = receiver.stop_session()
    assert stop_res["status"] == "receiver_stopped"
    assert receiver.is_active is False

