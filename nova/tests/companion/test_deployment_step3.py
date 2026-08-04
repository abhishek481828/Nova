"""Unit tests for Deployment Step 3: Secure Pairing & First Connection."""

import pytest
import asyncio
from nova.companion.security.pairing import PairingManager
from nova.companion.security.jwt_auth import JWTAuthManager
from nova.companion.security.ecdh import CryptoManager
from nova.companion.devices.device_manager import DeviceManager
from nova.companion.gateway.rest_api import (
    init_pairing,
    confirm_pairing,
    live_dashboard,
    PairingConfirmRequest
)


@pytest.mark.asyncio
async def test_pairing_init_and_qr_payload():
    res = await init_pairing(host="192.168.1.100", port=8000)
    assert res.pairing_id is not None
    assert len(res.pin) == 6
    assert res.pin.isdigit()

    qr = res.qr_payload
    assert qr["host"] == "192.168.1.100"
    assert qr["port"] == 8000
    assert qr["protocol_version"] == "2.0"
    assert "public_key" in qr


@pytest.mark.asyncio
async def test_pairing_confirm_success_and_jwt_issuance():
    pair_res = await init_pairing()
    pid = pair_res.pairing_id
    pin = pair_res.pin

    req = PairingConfirmRequest(
        pairing_id=pid,
        pin=pin,
        device_id="samsung-a13-test-01",
        device_name="Samsung Galaxy A13",
        platform="android",
        manufacturer="Samsung",
        model="Galaxy A13",
        android_version="12",
        sdk_version=31,
        companion_version="2.0.0",
        protocol_version="2.0",
        capabilities=["battery", "camera", "microphone", "notifications"]
    )

    conf_res = await confirm_pairing(req)
    assert conf_res.status == "paired"
    assert conf_res.device_id == "samsung-a13-test-01"
    assert conf_res.access_token is not None
    assert conf_res.refresh_token is not None

    # Verify token payload
    jwt_mgr = JWTAuthManager()
    payload = jwt_mgr.decode_and_verify_token(conf_res.access_token)
    assert payload["sub"] == "samsung-a13-test-01"


@pytest.mark.asyncio
async def test_pairing_confirm_invalid_pin():
    pair_res = await init_pairing()
    pid = pair_res.pairing_id

    req = PairingConfirmRequest(
        pairing_id=pid,
        pin="000000",  # Invalid PIN
        device_id="samsung-a13-test-02",
        device_name="Samsung Galaxy A13"
    )

    with pytest.raises(Exception):
        await confirm_pairing(req)


@pytest.mark.asyncio
async def test_device_registration_and_live_dashboard():
    # Confirm pairing to register device
    pair_res = await init_pairing()
    req = PairingConfirmRequest(
        pairing_id=pair_res.pairing_id,
        pin=pair_res.pin,
        device_id="samsung-a13-dash-01",
        device_name="Samsung Galaxy A13 Live",
        platform="android"
    )
    await confirm_pairing(req)

    # Fetch live dashboard
    dash = await live_dashboard()
    assert "total_devices" in dash
    assert dash["total_devices"] >= 1
    assert any(d["device_id"] == "samsung-a13-dash-01" for d in dash["devices"])


def test_ecdh_key_exchange():
    cm = CryptoManager()
    pub_bytes = cm.get_public_key_bytes()
    assert len(pub_bytes) > 0

    peer_cm = CryptoManager()
    peer_pub = peer_cm.get_public_key_bytes()

    shared_key1 = cm.derive_shared_secret(peer_pub)
    shared_key2 = peer_cm.derive_shared_secret(pub_bytes)
    assert shared_key1 == shared_key2
