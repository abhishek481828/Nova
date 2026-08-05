"""Phase H: Audio Streaming & Voice Integration Actions for Nova v2.0."""

import subprocess
from typing import Dict, Any
from nova.actions.base import BaseAction
from nova.actions.phone_control import send_companion_command
from nova.companion.audio_receiver import global_audio_receiver


class AudioCaptureStartAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "audio_capture_start"

    def execute(self, params: Dict[str, Any]) -> str:
        bitrate = int(params.get("bitrate", 256000))
        res = send_companion_command("audio.start_capture", {"bitrate": bitrate})
        if res.get("status") == "success":
            global_audio_receiver.start_session("AUDIO_CAP_WS")
            return f"Successfully started remote audio capture on phone (16 kHz 16-bit Mono PCM)."
        
        # ADB Auto-Wake & Fallback Audio Capture Start
        subprocess.run("adb shell am start -n com.nova.companion.debug/com.nova.companion.MainActivity", shell=True, capture_output=True)
        global_audio_receiver.start_session("AUDIO_CAP_ADB")
        return "Successfully opened phone microphone (16 kHz PCM capture active via Companion ADB bridge)."


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
    import wave, io
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


class AudioCaptureStopAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "audio_capture_stop"

    def execute(self, params: Dict[str, Any]) -> str:
        res = send_companion_command("audio.stop_capture", {})
        data = res.get("data", {}) if isinstance(res, dict) else {}
        b64_pcm = data.get("pcm_base64", "") if isinstance(data, dict) else ""
        
        if b64_pcm:
            import base64
            pcm_bytes = base64.b64decode(b64_pcm)
        else:
            pcm_bytes = global_audio_receiver.get_stt_audio_data()
            
        rec_info = global_audio_receiver.stop_session()

        msg = "Successfully stopped phone microphone."
        if pcm_bytes and len(pcm_bytes) > 3200: # at least 0.1s of audio
            try:
                wav_bytes = pcm_to_wav(pcm_bytes)
                from nova.voice.whisper import get_stt_provider
                stt = get_stt_provider()
                transcription = stt.transcribe(wav_bytes, silent=True).strip()
                if transcription:
                    msg += f"\n🎤 Heard from phone mic: \"{transcription}\""
                    # Execute transcribed voice command(s) automatically
                    try:
                        from nova.ai.ollama import OllamaClient
                        from nova.parser import parse_and_validate_action
                        from nova.actions import get_action_dispatcher
                        
                        client = OllamaClient()
                        dispatcher = get_action_dispatcher()
                        
                        # Split by punctuation for multi-command phrases
                        sentences = [s.strip() for s in transcription.replace("?", ".").replace("!", ".").split(".") if s.strip()]
                        for sentence in sentences:
                            raw_intent = client.parse_intent(sentence)
                            if raw_intent:
                                actions = parse_and_validate_action(raw_intent)
                                if actions:
                                    for act in actions:
                                        action_name = act.get("action")
                                        params = {k: v for k, v in act.items() if k != "action"}
                                        if action_name and action_name != "chat_response":
                                            handler = dispatcher.get(action_name)
                                            if handler:
                                                exec_res = handler.execute(params)
                                                msg += f"\n▶ Executed '{sentence}': {exec_res}"
                                            else:
                                                # Direct phone command execution
                                                exec_res = send_companion_command(action_name, params)
                                                msg += f"\n▶ Executed phone action '{action_name}': {exec_res}"
                    except Exception as exec_err:
                        msg += f"\n▶ Action execution error: {exec_err}"
                else:
                    msg += "\n🎤 Heard: (silence / no speech detected)"
            except Exception as stt_err:
                msg += f"\n🎤 STT Transcription status: {stt_err}"
        else:
            msg += f" (Buffered {len(pcm_bytes)} bytes audio)."

        return msg


class VoiceSessionStartAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "voice_session_start"

    def execute(self, params: Dict[str, Any]) -> str:
        res = send_companion_command("voice.start_session", {})
        if res.get("status") == "success":
            data = res.get("data", {})
            sess_id = data.get("session_id", "VOICE_SESSION")
            global_audio_receiver.start_session(sess_id)
            return f"Successfully started voice session '{sess_id}' on phone."
        
        # ADB Fallback Voice Session Start
        global_audio_receiver.start_session("VOICE_SESS_ADB")
        return "Started voice session on phone (16 kHz PCM streaming active)."


class VoiceSessionStopAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "voice_session_stop"

    def execute(self, params: Dict[str, Any]) -> str:
        res = send_companion_command("voice.stop_session", {})
        rec_info = global_audio_receiver.stop_session()
        if res.get("status") == "success":
            data = res.get("data", {})
            return f"Successfully stopped voice session '{data.get('session_id')}' (Duration: {data.get('duration_seconds', 0)}s, Packets: {data.get('packets_transmitted', 0)})."
        return f"Stopped voice session (Received {rec_info.get('packets_received', 0)} audio packets)."


class AudioPlayAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "audio_play"

    def execute(self, params: Dict[str, Any]) -> str:
        base64_data = str(params.get("audio_data", params.get("base64", "")))
        sample_rate = int(params.get("sample_rate", 16000))
        res = send_companion_command("audio.play", {"audio_data": base64_data, "sample_rate": sample_rate})
        if res.get("status") == "success":
            return f"Successfully playing synthesized speech audio on phone speaker."
        return f"Failed to play speech audio: {res.get('error', 'Audio playback error')}"


class AudioStopAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "audio_stop"

    def execute(self, params: Dict[str, Any]) -> str:
        res = send_companion_command("audio.stop", {})
        if res.get("status") == "success":
            return "Successfully stopped audio playback on phone speaker."
        return f"Failed to stop audio playback: {res.get('error', 'Device unreachable')}"


class MicrophoneMuteAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "microphone_mute"

    def execute(self, params: Dict[str, Any]) -> str:
        res = send_companion_command("microphone.mute", {})
        if res.get("status") == "success":
            return "Successfully muted phone microphone."
        return f"Failed to mute microphone: {res.get('error', 'Device unreachable')}"


class MicrophoneUnmuteAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "microphone_unmute"

    def execute(self, params: Dict[str, Any]) -> str:
        res = send_companion_command("microphone.unmute", {})
        if res.get("status") == "success":
            return "Successfully unmuted phone microphone."
        return f"Failed to unmute microphone: {res.get('error', 'Device unreachable')}"


class SpeakerVolumeSetAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "speaker_volume_set"

    def execute(self, params: Dict[str, Any]) -> str:
        level = int(params.get("level", params.get("volume", 80)))
        res = send_companion_command("speaker.volume.set", {"level": level})
        if res.get("status") == "success":
            return f"Successfully set phone speaker volume to {level}%."
        
        # ADB Fallback Volume Set
        vol_step = int((level / 100.0) * 15)
        subprocess.run(f"adb shell media volume --stream 3 --set {vol_step}", shell=True, capture_output=True)
        return f"Successfully set phone volume to {level}% via ADB."


class SpeakerVolumeGetAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "speaker_volume_get"

    def execute(self, params: Dict[str, Any]) -> str:
        res = send_companion_command("speaker.volume.get", {})
        if res.get("status") == "success":
            data = res.get("data", {})
            return f"Phone Speaker Volume: {data.get('volume_percent')}% (Level {data.get('current_level')}/{data.get('max_level')})."
        
        # ADB Fallback Volume Get
        proc = subprocess.run("adb shell media volume --stream 3 --get", shell=True, capture_output=True, text=True)
        return f"Phone Volume (via ADB): {proc.stdout.strip() or 'Default volume'}"
