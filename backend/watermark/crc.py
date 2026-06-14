"""
CRC-8/SMBUS checksum computation for the 28-bit watermark payload.

Polynomial : 0x07
Init value : 0x00
Reflection : none (no input/output reflection)
Final XOR  : none
"""

import logging

logger = logging.getLogger(__name__)

_CRC8_DATA_BITS = 28
_CRC8_TOTAL_BITS = 32   # padded to 4 full bytes
_CRC8_RESULT_BITS = 8
_FULL_PAYLOAD_BITS = _CRC8_DATA_BITS + _CRC8_RESULT_BITS  # 36
_POLYNOMIAL = 0x07


def _pack_bits_to_byte(bits: list[int], offset: int) -> int:
    """Pack 8 consecutive bits (MSB-first) into an integer byte value."""
    byte_val = 0
    for bit_idx in range(8):
        byte_val = (byte_val << 1) | bits[offset + bit_idx]
    return byte_val


def _crc8_of_bytes(data_bytes: list[int]) -> int:
    """Run the CRC-8/SMBUS algorithm over a list of integer byte values."""
    crc = 0x00
    for byte_val in data_bytes:
        crc ^= byte_val
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ _POLYNOMIAL
            else:
                crc <<= 1
            crc &= 0xFF
    return crc


def compute_crc8(bits: list[int]) -> list[int]:
    """
    Compute CRC-8/SMBUS over a 28-bit payload.

    The payload is zero-padded on the right to 32 bits (4 bytes) before
    the CRC is computed, matching the WATERMARK_SPEC.md algorithm exactly.

    Args:
        bits: Exactly 28 ints, each 0 or 1, MSB first.

    Returns:
        List of 8 ints (each 0 or 1) representing the CRC byte, MSB first.

    Raises:
        ValueError: If ``bits`` does not have exactly 28 elements, or if
                    any element is not 0 or 1.
    """
    if len(bits) != _CRC8_DATA_BITS:
        raise ValueError(
            f"compute_crc8 expects {_CRC8_DATA_BITS} bits, got {len(bits)}"
        )
    if any(b not in (0, 1) for b in bits):
        raise ValueError("All elements of bits must be 0 or 1")

    padded: list[int] = bits + [0] * (_CRC8_TOTAL_BITS - _CRC8_DATA_BITS)

    data_bytes = [
        _pack_bits_to_byte(padded, byte_idx * 8)
        for byte_idx in range(_CRC8_TOTAL_BITS // 8)
    ]

    crc = _crc8_of_bytes(data_bytes)

    result: list[int] = [(crc >> (7 - i)) & 1 for i in range(_CRC8_RESULT_BITS)]
    logger.debug("compute_crc8: input_bits=%d crc=0x%02X", len(bits), crc)
    return result


def verify_crc8(bits: list[int]) -> bool:
    """
    Verify the CRC-8 appended to a 36-bit watermark payload.

    Recomputes CRC-8 over ``bits[:28]`` and compares it to ``bits[28:36]``.

    Args:
        bits: Exactly 36 ints, each 0 or 1 — 28 data bits followed by
              8 CRC bits, all MSB first.

    Returns:
        True if the recomputed CRC matches the embedded CRC; False otherwise.

    Raises:
        ValueError: If ``bits`` does not have exactly 36 elements, or if
                    any element is not 0 or 1.
    """
    if len(bits) != _FULL_PAYLOAD_BITS:
        raise ValueError(
            f"verify_crc8 expects {_FULL_PAYLOAD_BITS} bits, got {len(bits)}"
        )
    if any(b not in (0, 1) for b in bits):
        raise ValueError("All elements of bits must be 0 or 1")

    expected: list[int] = compute_crc8(bits[:_CRC8_DATA_BITS])
    actual: list[int] = bits[_CRC8_DATA_BITS:_FULL_PAYLOAD_BITS]
    match = expected == actual
    logger.debug("verify_crc8: match=%s", match)
    return match
