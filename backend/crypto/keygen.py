"""
Cryptographic key generation and base64 serialisation helpers.
Pure computation — no I/O, no database, no HTTP.
"""

import base64
import secrets

KEY_SIZE_BYTES: int = 32  # 256 bits for AES-256


def generate_key() -> bytes:
    """Return 32 cryptographically random bytes."""
    return secrets.token_bytes(KEY_SIZE_BYTES)


def key_to_b64(key: bytes) -> str:
    """Encode key bytes as a URL-safe base64 string."""
    return base64.urlsafe_b64encode(key).decode("ascii")


def b64_to_key(b64: str) -> bytes:
    """
    Decode a URL-safe base64 string back to key bytes.
    Raises ValueError if the result is not 32 bytes.
    """
    key = base64.urlsafe_b64decode(b64.encode("ascii"))
    if len(key) != KEY_SIZE_BYTES:
        raise ValueError(
            f"Decoded key must be {KEY_SIZE_BYTES} bytes, got {len(key)}"
        )
    return key
