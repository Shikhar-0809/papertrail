"""
Tests for backend/crypto/aes.py and backend/crypto/keygen.py.
No mocking — all tests use the real encrypt/decrypt/keygen functions.
"""

import pytest
from cryptography.exceptions import InvalidTag

from backend.crypto.aes import NONCE_SIZE_BYTES, decrypt, encrypt
from backend.crypto.keygen import b64_to_key, generate_key, key_to_b64


# ---------------------------------------------------------------------------
# AES-256-GCM
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip() -> None:
    key = generate_key()
    plaintext = b"exam paper content"
    assert decrypt(encrypt(plaintext, key), key) == plaintext


def test_encrypt_produces_different_nonce_each_time() -> None:
    key = generate_key()
    plaintext = b"same content"
    c1 = encrypt(plaintext, key)
    c2 = encrypt(plaintext, key)
    assert c1 != c2


def test_nonce_is_prepended_to_ciphertext() -> None:
    key = generate_key()
    ct = encrypt(b"data", key)
    assert len(ct) > NONCE_SIZE_BYTES
    # nonces of two separate encryptions must differ
    assert encrypt(b"data", key)[:NONCE_SIZE_BYTES] != ct[:NONCE_SIZE_BYTES]


def test_decrypt_wrong_key_raises_invalid_tag() -> None:
    key1 = generate_key()
    key2 = generate_key()
    ciphertext = encrypt(b"secret", key1)
    with pytest.raises(InvalidTag):
        decrypt(ciphertext, key2)


def test_decrypt_tampered_ciphertext_raises_invalid_tag() -> None:
    key = generate_key()
    ciphertext = bytearray(encrypt(b"secret exam", key))
    ciphertext[len(ciphertext) // 2] ^= 0xFF
    with pytest.raises(InvalidTag):
        decrypt(bytes(ciphertext), key)


def test_wrong_key_length_raises_value_error() -> None:
    with pytest.raises(ValueError, match="32-byte"):
        encrypt(b"data", b"tooshort")
    with pytest.raises(ValueError, match="32-byte"):
        decrypt(b"data", b"tooshort")


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def test_keygen_produces_32_bytes() -> None:
    assert len(generate_key()) == 32


def test_keygen_produces_different_keys() -> None:
    assert generate_key() != generate_key()


def test_key_b64_roundtrip() -> None:
    key = generate_key()
    assert b64_to_key(key_to_b64(key)) == key


def test_b64_to_key_wrong_length_raises() -> None:
    bad = key_to_b64(b"tooshort")
    with pytest.raises(ValueError):
        b64_to_key(bad)
