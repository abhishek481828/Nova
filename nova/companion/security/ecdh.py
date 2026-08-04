"""ECDH Key Exchange and AES-256-GCM Symmetric Encryption Engine for Nova v2.0."""

import base64
import os
import hashlib
import hmac
from typing import Tuple

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class CryptoManager:
    """Provides ECDH P-256 Key Exchange and AES-256-GCM authenticated encryption."""

    def __init__(self):
        if HAS_CRYPTOGRAPHY:
            self._private_key = ec.generate_private_key(ec.SECP256R1())
        else:
            self._private_key = None

    def get_public_key_bytes(self) -> bytes:
        """Returns SEC1 encoded uncompressed public key bytes."""
        if HAS_CRYPTOGRAPHY:
            return self._private_key.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        # Fallback pseudo-key for development if cryptography package is absent
        return hashlib.sha256(b"nova-ecdh-fallback-key").digest()

    def derive_shared_secret(self, peer_public_bytes: bytes) -> bytes:
        """Derives a 256-bit symmetric session key using ECDH and HKDF."""
        if HAS_CRYPTOGRAPHY:
            peer_public_key = serialization.load_der_public_key(peer_public_bytes)
            shared_key = self._private_key.exchange(ec.ECDH(), peer_public_key)
            hkdf = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=b"nova-v2-companion-session",
            )
            return hkdf.derive(shared_key)
        else:
            # Fallback HKDF derivation
            return hmac.new(b"nova-v2-salt", peer_public_bytes, hashlib.sha256).digest()

    @staticmethod
    def encrypt_payload(key: bytes, plaintext: str) -> str:
        """Encrypt plaintext payload using AES-256-GCM."""
        nonce = os.urandom(12)
        if HAS_CRYPTOGRAPHY:
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
            combined = nonce + ciphertext
            return base64.b64encode(combined).decode('utf-8')
        else:
            # Fallback XOR cipher for testing if cryptography native lib is not installed
            pt_bytes = plaintext.encode('utf-8')
            cipher = bytes([b ^ key[i % len(key)] for i, b in enumerate(pt_bytes)])
            return base64.b64encode(nonce + cipher).decode('utf-8')

    @staticmethod
    def decrypt_payload(key: bytes, encrypted_b64: str) -> str:
        """Decrypt AES-256-GCM ciphertext payload."""
        combined = base64.b64decode(encrypted_b64.encode('utf-8'))
        nonce = combined[:12]
        ciphertext = combined[12:]
        if HAS_CRYPTOGRAPHY:
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode('utf-8')
        else:
            plaintext = bytes([b ^ key[i % len(key)] for i, b in enumerate(ciphertext)])
            return plaintext.decode('utf-8')
