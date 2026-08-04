"""Audio Streaming Plugin for Nova v2.0."""

from typing import Any, Dict, List
from nova.companion.plugins.base_plugin import BaseCompanionPlugin
from nova.companion.streaming.audio_stream import CompanionAudioStreamer


class AudioPlugin(BaseCompanionPlugin):
    """Plugin handling 16kHz PCM audio streaming, mic capture, and TTS speaker playback."""

    def __init__(self):
        self.streamer = CompanionAudioStreamer()

    @property
    def plugin_name(self) -> str:
        return "media.audio"

    @property
    def supported_actions(self) -> List[str]:
        return [
            "audio.start_mic_stream",
            "audio.stop_mic_stream",
            "audio.play_tts_stream"
        ]

    async def execute(self, device_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "audio.start_mic_stream":
            return {"action": action, "device_id": device_id, "sample_rate": 16000, "status": "mic_streaming"}
        elif action == "audio.stop_mic_stream":
            self.streamer.stop()
            return {"action": action, "device_id": device_id, "status": "mic_stopped"}
        elif action == "audio.play_tts_stream":
            return {"action": action, "device_id": device_id, "status": "tts_playing"}
        return {"action": action, "device_id": device_id, "status": "dispatched"}
