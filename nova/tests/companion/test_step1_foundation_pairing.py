"""End-to-end integration test for Step 1: Foundation & Pairing."""

import pytest
import asyncio

from nova.companion.security.pairing import PairingManager
from nova.companion.security.jwt_auth import JWTAuthManager
from nova.companion.gateway.rest_api import init_pairing, confirm_pairing, PairingConfirmRequest
from nova.companion.gateway.websocket_server import device_mgr
from nova.companion.protocol.schemas import HeartbeatMessage

jwt_mgr = JWTAuthManager()


@pytest.mark.asyncio
async def test_step1_pairing_and_jwt_issuance():
    # 1. Init pairing session
    res_init = await init_pairing(host="127.0.0.1", port=8000)
    pairing_id = res_init.pairing_id
    pin = res_init.pin

    assert len(pin) == 6

    # 2. Confirm pairing with PIN
    req_payload = PairingConfirmRequest(
        pairing_id=pairing_id,
        pin=pin,
        device_id="galaxy-a13-uuid-1234",
        device_name="Samsung Galaxy A13",
        platform="android",
        capabilities=["flashlight", "battery", "gps"]
    )
    confirm_data = await confirm_pairing(req_payload)

    assert confirm_data.status == "paired"
    assert confirm_data.device_id == "galaxy-a13-uuid-1234"
    access_token = confirm_data.access_token
    assert access_token is not None

    # 3. Verify JWT token claims
    payload = jwt_mgr.decode_and_verify_token(access_token)
    assert payload["sub"] == "galaxy-a13-uuid-1234"
    assert payload["platform"] == "android"


def test_step1_heartbeat_processing():
    device_id = "galaxy-a13-uuid-1234"
    hb = HeartbeatMessage(
        device_id=device_id,
        battery_level=88,
        is_charging=True,
        status="online"
    )
    device_mgr.record_heartbeat(hb)

    assert device_mgr.is_online(device_id) is True
    telemetry = device_mgr.get_telemetry(device_id)
    assert telemetry["battery_level"] == 88
    assert telemetry["is_charging"] is True
