"""
Exhaustive tests for backend/watermark/crc.py.

Covers:
  - Output shape and value-domain of compute_crc8
  - Roundtrip (compute then verify) for several payloads
  - Every single-bit flip in both the data field and the CRC field is detected
  - ValueError on every wrong-length input
"""

import pytest

from backend.watermark.crc import compute_crc8, verify_crc8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _int_to_bits(value: int, width: int) -> list[int]:
    """Convert an unsigned integer to a fixed-width MSB-first bit list."""
    return [(value >> (width - 1 - i)) & 1 for i in range(width)]


def _make_payload(center_id: int, exam_id: int, page_num: int) -> list[int]:
    """Build the 28-bit data payload from the three watermark fields."""
    return (
        _int_to_bits(center_id, 16)
        + _int_to_bits(exam_id, 8)
        + _int_to_bits(page_num, 4)
    )


def _valid_36_bits() -> list[int]:
    """Return a known-good 36-bit sequence (center=221, exam=1, page=1)."""
    data = _make_payload(221, 1, 1)
    return data + compute_crc8(data)


# ---------------------------------------------------------------------------
# Output shape / value-domain
# ---------------------------------------------------------------------------

def test_crc_output_is_8_bits() -> None:
    result = compute_crc8([0] * 28)
    assert len(result) == 8, f"Expected 8 bits, got {len(result)}"
    assert all(b in (0, 1) for b in result), "CRC bits must all be 0 or 1"


# ---------------------------------------------------------------------------
# Roundtrip tests
# ---------------------------------------------------------------------------

def test_crc_roundtrip_all_zeros() -> None:
    data = [0] * 28
    assert verify_crc8(data + compute_crc8(data)) is True


def test_crc_roundtrip_all_ones() -> None:
    data = [1] * 28
    assert verify_crc8(data + compute_crc8(data)) is True


def test_crc_roundtrip_center_221() -> None:
    data = _make_payload(center_id=221, exam_id=1, page_num=1)
    assert len(data) == 28
    crc = compute_crc8(data)
    assert len(crc) == 8
    assert verify_crc8(data + crc) is True


def test_crc_roundtrip_center_65535() -> None:
    data = _make_payload(center_id=65535, exam_id=255, page_num=15)
    assert verify_crc8(data + compute_crc8(data)) is True


# ---------------------------------------------------------------------------
# Single-bit flip detection — data field (bits 0–27)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("flip_pos", range(28))
def test_crc_detects_every_single_bit_flip_in_data(flip_pos: int) -> None:
    bits = _valid_36_bits()
    flipped = bits[:flip_pos] + [1 - bits[flip_pos]] + bits[flip_pos + 1:]
    assert verify_crc8(flipped) is False, (
        f"Flip at data bit {flip_pos} was not detected by CRC"
    )


# ---------------------------------------------------------------------------
# Single-bit flip detection — CRC field (bits 28–35)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("flip_pos", range(28, 36))
def test_crc_detects_every_single_bit_flip_in_crc_field(flip_pos: int) -> None:
    bits = _valid_36_bits()
    flipped = bits[:flip_pos] + [1 - bits[flip_pos]] + bits[flip_pos + 1:]
    assert verify_crc8(flipped) is False, (
        f"Flip at CRC bit {flip_pos} was not detected"
    )


# ---------------------------------------------------------------------------
# ValueError on wrong-length input
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_length", [0, 1, 27, 29, 36, 100])
def test_compute_crc8_raises_on_wrong_length(bad_length: int) -> None:
    with pytest.raises(ValueError):
        compute_crc8([0] * bad_length)


@pytest.mark.parametrize("bad_length", [0, 1, 28, 35, 37, 100])
def test_verify_crc8_raises_on_wrong_length(bad_length: int) -> None:
    with pytest.raises(ValueError):
        verify_crc8([0] * bad_length)


# ---------------------------------------------------------------------------
# Hardcoded ground-truth vectors from WATERMARK_SPEC.md
# ---------------------------------------------------------------------------

def test_crc_known_vectors() -> None:
    """
    CRC values verified against WATERMARK_SPEC.md test vectors.
    These are hardcoded ground truth — if compute_crc8 ever changes
    behavior, this test catches it immediately.
    """
    vectors = [
        # (center_id, exam_id, page_num, expected_crc_int)
        (1,     1, 1, 0x0E),
        (221,   1, 1, 0xDB),
        (442,   1, 1, 0x1E),
        (65535, 255, 15, 0xF3),
    ]
    for center_id, exam_id, page_num, expected_crc_int in vectors:
        bits_28 = (
            [(center_id >> (15 - i)) & 1 for i in range(16)] +
            [(exam_id   >> (7  - i)) & 1 for i in range(8)]  +
            [(page_num  >> (3  - i)) & 1 for i in range(4)]
        )
        crc_bits = compute_crc8(bits_28)
        crc_int = int("".join(str(b) for b in crc_bits), 2)
        assert crc_int == expected_crc_int, (
            f"center_id={center_id}: expected CRC 0x{expected_crc_int:02X}, "
            f"got 0x{crc_int:02X}"
        )
        assert verify_crc8(bits_28 + crc_bits) is True
