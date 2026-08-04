"""Unit tests for Nova v2.0 Protocol, Schemas & Framing."""

import pytest
from nova.companion.protocol.schemas import (
    CommandMessage, ResponseMessage, HeartbeatMessage, MessageType, CommandStatus
)
from nova.companion.protocol.framing import (
    parse_json_frame, serialize_json_frame, create_binary_audio_frame, unpack_binary_audio_frame
)
from nova.companion.protocol.version_negotiator import VersionNegotiator
from nova.companion.protocol.capability_discovery import CapabilityDiscoveryEngine, CapabilityAdvertisement


def test_command_message_serialization():
    cmd = CommandMessage(target="device-123", action="flashlight.on", payload={"brightness": 100})
    json_str = serialize_json_frame(cmd)
    parsed = parse_json_frame(json_str)

    assert isinstance(parsed, CommandMessage)
    assert parsed.target == "device-123"
    assert parsed.action == "flashlight.on"
    assert parsed.payload["brightness"] == 100


def test_binary_audio_framing():
    seq = 42
    ts = 1754300000123
    data = b"\x01\x02\x03\x04\x05\x06"

    frame = create_binary_audio_frame(seq, ts, data)
    unpacked_seq, unpacked_ts, unpacked_data = unpack_binary_audio_frame(frame)

    assert unpacked_seq == seq
    assert unpacked_ts == ts
    assert unpacked_data == data


def test_version_negotiator():
    assert VersionNegotiator.negotiate("2.0.0") == "2.0.0"
    assert VersionNegotiator.negotiate("2.2.0") == "2.2.0"


def test_capability_discovery():
    engine = CapabilityDiscoveryEngine()
    ad = CapabilityAdvertisement(
        device_id="dev-1",
        device_name="Test Phone",
        platform="android",
        capabilities=["flashlight", "battery", "gps"]
    )
    engine.register_capabilities(ad)

    assert engine.has_capability("dev-1", "flashlight") is True
    assert engine.has_capability("dev-1", "camera") is False
    assert "dev-1" in engine.find_devices_with_capability("gps")
