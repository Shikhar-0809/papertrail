"""
AES-256-GCM encryption and decryption.
Pure computation — no I/O, no database, no HTTP.
"""

import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

NONCE_SIZE_BYTES: int = 12  # 96-bit nonce, standard for GCM
TAG_SIZE_BYTES: int = 16    # 128-bit authentication tag (cryptography lib default)

_KEY_SIZE_BYTES: int = 32   # AES-256


def _validate_key(key: bytes) -> None:
    if len(key) != _KEY_SIZE_BYTES:
        raise ValueError("AES-256 requires a 32-byte key")


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """
    Encrypt plaintext with AES-256-GCM.

    Returns nonce + ciphertext + tag as a single bytes object.
    Generates a fresh random nonce on every call.
    Raises ValueError if key is not 32 bytes.
    """
    _validate_key(key)
    nonce = os.urandom(NONCE_SIZE_BYTES)
    aesgcm = AESGCM(key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext, None)
    logger.debug("encrypt: produced %d bytes (nonce=%d body=%d)",
                 NONCE_SIZE_BYTES + len(ciphertext_and_tag),
                 NONCE_SIZE_BYTES, len(ciphertext_and_tag))
    return nonce + ciphertext_and_tag


def decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """
    Decrypt output of encrypt().

    Expects nonce prepended to ciphertext+tag (as produced by encrypt()).
    Raises ValueError if key is not 32 bytes.
    Raises cryptography.exceptions.InvalidTag if authentication fails —
    does NOT catch it; callers must handle tamper detection.
    """
    _validate_key(key)
    nonce = ciphertext[:NONCE_SIZE_BYTES]
    body = ciphertext[NONCE_SIZE_BYTES:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, body, None)
