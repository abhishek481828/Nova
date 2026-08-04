"""Unit tests for Security, Cryptography, JWT & Pairing."""

import pytest
from nova.companion.security.ecdh import CryptoManager
from nova.companion.security.jwt_auth import JWTAuthManager
from nova.companion.security.pairing import PairingManager


def test_crypto_manager_encrypt_decrypt():
    key = b"12345678901234567890123456789012"  # 32 bytes
    plaintext = "Hello Nova v2.0 Companion Security"

    encrypted = CryptoManager.encrypt_payload(key, plaintext)
    decrypted = CryptoManager.decrypt_payload(key, encrypted)

    assert decrypted == plaintext


def test_jwt_auth_manager():
    jwt_mgr = JWTAuthManager(secret_key="test_secret_key")
    token = jwt_mgr.create_access_token(device_id="phone-77", platform="android")

    payload = jwt_mgr.decode_and_verify_token(token)
    assert payload["sub"] == "phone-77"
    assert payload["platform"] == "android"


def test_pairing_manager():
    mgr = PairingManager(session_ttl_seconds=60)
    pairing_id, pin, qr_payload = mgr.create_pairing_session("127.0.0.1", 8000)

    assert len(pin) == 6
    assert mgr.verify_pin(pairing_id, pin) is True
    # Re-use should fail
    assert mgr.verify_pin(pairing_id, pin) is False
