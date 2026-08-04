"""Phase H: Nova Core Audio Receiver for Companion PCM Streaming."""

import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("nova.companion.audio_receiver")


class AudioReceiver:
    def __init__(self):
        self.is_active = False
        self.last_sequence = 0
        self.total_packets_received = 0
        self.dropped_packets = 0
        self.buffer = bytearray()
        self.session_id: Optional[str] = None

    def start_session(self, session_id: str) -> Dict[str, Any]:
        self.is_active = True
        self.session_id = session_id
        self.last_sequence = 0
        self.total_packets_received = 0
        self.dropped_packets = 0
        self.buffer.clear()
        logger.info(f"AudioReceiver session started: {session_id}")
        return {"status": "receiver_started", "session_id": session_id}

    def stop_session(self) -> Dict[str, Any]:
        self.is_active = False
        logger.info(f"AudioReceiver session stopped: {self.session_id} (Received {self.total_packets_received} packets, {self.dropped_packets} dropped)")
        res = {
            "status": "receiver_stopped",
            "session_id": self.session_id,
            "packets_received": self.total_packets_received,
            "dropped_packets": self.dropped_packets,
            "buffer_size_bytes": len(self.buffer)
        }
        self.session_id = None
        return res

    def process_pcm_packet(self, packet_header: Dict[str, Any], pcm_bytes: bytes) -> Dict[str, Any]:
        if not self.is_active:
            return {"status": "inactive"}

        seq = int(packet_header.get("seq", self.last_sequence + 1))
        
        # Sequence validation & packet loss detection
        if self.last_sequence > 0 and seq > self.last_sequence + 1:
            missing = seq - (self.last_sequence + 1)
            self.dropped_packets += missing
            logger.warning(f"Packet loss detected in audio stream: missed {missing} packets (Expected {self.last_sequence + 1}, got {seq})")

        self.last_sequence = seq
        self.total_packets_received += 1
        self.buffer.extend(pcm_bytes)

        return {
            "status": "packet_processed",
            "seq": seq,
            "bytes": len(pcm_bytes),
            "total_bytes": len(self.buffer),
            "dropped_count": self.dropped_packets
        }

    def get_stt_audio_data(self) -> bytes:
        """Returns collected PCM audio stream for Nova Speech-to-Text processing."""
        data = bytes(self.buffer)
        self.buffer.clear()
        return data


# Global Singleton AudioReceiver instance
global_audio_receiver = AudioReceiver()
