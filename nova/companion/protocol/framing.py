"""Message framing and serialization helpers for Nova v2.0."""

import json
import struct
from typing import Any, Dict, Tuple, Union
from nova.companion.protocol.schemas import (
    BaseMessage,
    CommandMessage,
    ResponseMessage,
    EventMessage,
    HeartbeatMessage,
    HandshakeMessage,
    MessageType,
)

# Header constants for binary stream framing
BINARY_FRAME_AUDIO = 0x0A
BINARY_FRAME_VIDEO = 0x56   # ASCII 'V' (0x56)
BINARY_FRAME_FILE = 0x46    # ASCII 'F' (0x46)


class ProtocolFramingError(Exception):
    """Raised when frame serialization or deserialization fails."""
    pass


def parse_json_frame(raw_str: str) -> BaseMessage:
    """Parse a raw JSON string frame into a strongly-typed message model."""
    try:
        data = json.loads(raw_str)
        msg_type = data.get("type")
        if msg_type == MessageType.COMMAND:
            return CommandMessage(**data)
        elif msg_type == MessageType.RESPONSE:
            return ResponseMessage(**data)
        elif msg_type == MessageType.EVENT:
            return EventMessage(**data)
        elif msg_type == MessageType.HEARTBEAT:
            return HeartbeatMessage(**data)
        elif msg_type == MessageType.HANDSHAKE:
            return HandshakeMessage(**data)
        else:
            return BaseMessage(**data)
    except Exception as e:
        raise ProtocolFramingError(f"Failed to parse JSON frame: {e}") from e


def serialize_json_frame(msg: BaseMessage) -> str:
    """Serialize a message model into a JSON string."""
    return msg.model_dump_json()


def create_binary_audio_frame(seq_num: int, timestamp_ms: int, audio_bytes: bytes) -> bytes:
    """Format an audio frame into binary format:
    Header (1b) + SeqNum (4b, uint32) + TimestampMs (8b, uint64) + Payload
    """
    header = struct.pack(">BIQ", BINARY_FRAME_AUDIO, seq_num, timestamp_ms)
    return header + audio_bytes


def unpack_binary_audio_frame(frame: bytes) -> Tuple[int, int, bytes]:
    """Unpack a binary audio frame. Returns (seq_num, timestamp_ms, audio_bytes)."""
    if len(frame) < 13 or frame[0] != BINARY_FRAME_AUDIO:
        raise ProtocolFramingError("Invalid binary audio frame header")
    _, seq_num, timestamp_ms = struct.unpack(">BIQ", frame[:13])
    audio_bytes = frame[13:]
    return seq_num, timestamp_ms, audio_bytes
