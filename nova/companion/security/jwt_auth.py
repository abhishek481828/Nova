"""JWT Token Management and Validation Engine for Nova v2.0."""

import time
import hmac
import hashlib
import json
import base64
import secrets
from typing import Any, Dict, Optional

DEFAULT_SECRET = "nova_v2_companion_jwt_secret_key_change_in_production"
ACCESS_TOKEN_EXPIRE_SECONDS = 3600 * 24        # 24 hours
REFRESH_TOKEN_EXPIRE_SECONDS = 3600 * 24 * 30   # 30 days


class JWTAuthManager:
    def __init__(self, secret_key: str = DEFAULT_SECRET):
        self.secret_key = secret_key.encode('utf-8')

    def _b64_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

    def _b64_decode(self, data_str: str) -> bytes:
        padding = 4 - (len(data_str) % 4)
        if padding and padding != 4:
            data_str += '=' * padding
        return base64.urlsafe_b64decode(data_str.encode('utf-8'))

    def create_access_token(self, device_id: str, platform: str, scopes: Optional[list] = None) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        now = time.time()
        payload = {
            "sub": device_id,
            "platform": platform,
            "scopes": scopes or ["companion:all"],
            "iat": int(now),
            "exp": int(now + ACCESS_TOKEN_EXPIRE_SECONDS),
            "jti": secrets.token_hex(8)
        }
        
        encoded_header = self._b64_encode(json.dumps(header).encode('utf-8'))
        encoded_payload = self._b64_encode(json.dumps(payload).encode('utf-8'))
        
        signature_input = f"{encoded_header}.{encoded_payload}".encode('utf-8')
        signature = hmac.new(self.secret_key, signature_input, hashlib.sha256).digest()
        encoded_sig = self._b64_encode(signature)
        
        return f"{encoded_header}.{encoded_payload}.{encoded_sig}"

    def create_refresh_token(self, device_id: str) -> str:
        return secrets.token_urlsafe(32)

    def decode_and_verify_token(self, token: str) -> Dict[str, Any]:
        """Decodes and validates a JWT token. Raises ValueError on invalid/expired token."""
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT structure")

        encoded_header, encoded_payload, encoded_sig = parts
        
        signature_input = f"{encoded_header}.{encoded_payload}".encode('utf-8')
        expected_sig = hmac.new(self.secret_key, signature_input, hashlib.sha256).digest()
        
        if not hmac.compare_digest(self._b64_decode(encoded_sig), expected_sig):
            raise ValueError("Invalid JWT signature")

        payload = json.loads(self._b64_decode(encoded_payload).decode('utf-8'))
        
        if time.time() > payload.get("exp", 0):
            raise ValueError("JWT token has expired")

        return payload
