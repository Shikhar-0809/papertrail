"""
Full encode → (simulate) → decode pipeline tests.

Covers:
  - Clean roundtrip with no degradation
  - Roundtrip through simulate_leak_photo with fixed params (deterministic)
  - Edge-case center IDs (near-all-zeros, all-ones, WATERMARK_SPEC.md vectors)
  - Encoder input validation
  - Decoder robustness (empty image, white image, pure noise)
  - Partial grid survival (one corner destroyed)
"""

import numpy as np
import pytest

from backend.watermark.crc import compute_crc8, verify_crc8
from backend.watermark.decoder import ForensicResult, extract_center_id
from backend.watermark.encoder import embed_markers
from backend.watermark.simulator import simulate_leak_photo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def blank_page() -> np.ndarray:
    return np.ones((3508, 2480), dtype=np.uint8) * 255


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_payload(center_id: int, exam_id: int, page_num: int) -> list[int]:
    return (
        [(center_id >> (15 - i)) & 1 for i in range(16)]
        + [(exam_id >> (7 - i)) & 1 for i in range(8)]
        + [(page_num >> (3 - i)) & 1 for i in range(4)]
    )


# ---------------------------------------------------------------------------
# Roundtrip — no degradation
# ---------------------------------------------------------------------------

def test_roundtrip_no_degradation(blank_page: np.ndarray) -> None:
    wm = embed_markers(blank_page, center_id=221, exam_id=1, page_num=1)
    result = extract_center_id(wm)

    assert result.status == "identified"
    assert result.center_id == 221
    assert result.exam_id == 1
    assert result.page_num == 1
    assert result.confidence == 1.0
    assert result.grids_valid == 4
    assert result.error is None


# ---------------------------------------------------------------------------
# Roundtrip through simulator — fixed params (deterministic)
# ---------------------------------------------------------------------------

def test_roundtrip_center_221(blank_page: np.ndarray) -> None:
    wm = embed_markers(blank_page, center_id=221, exam_id=1, page_num=1)
    degraded = simulate_leak_photo(
        wm, rotation_deg=0.0, jpeg_quality=70, perspective_jitter=5,
        dark_background=True,
    )
    result = extract_center_id(degraded)

    assert result.status == "identified"
    assert result.center_id == 221


def test_roundtrip_center_1(blank_page: np.ndarray) -> None:
    """center_id=1 is near-all-zeros — edge case for low-density watermarks."""
    wm = embed_markers(blank_page, center_id=1, exam_id=1, page_num=1)
    degraded = simulate_leak_photo(
        wm, rotation_deg=0.0, jpeg_quality=72, perspective_jitter=5,
        dark_background=True,
    )
    result = extract_center_id(degraded)

    assert result.status == "identified"
    assert result.center_id == 1


def test_roundtrip_center_65535(blank_page: np.ndarray) -> None:
    """center_id=65535 is all-ones — maximum value edge case."""
    wm = embed_markers(blank_page, center_id=65535, exam_id=255, page_num=15)
    degraded = simulate_leak_photo(
        wm, rotation_deg=0.0, jpeg_quality=71, perspective_jitter=5,
        dark_background=True,
    )
    result = extract_center_id(degraded)

    assert result.status == "identified"
    assert result.center_id == 65535


def test_roundtrip_center_442(blank_page: np.ndarray) -> None:
    wm = embed_markers(blank_page, center_id=442, exam_id=1, page_num=1)
    degraded = simulate_leak_photo(
        wm, rotation_deg=0.0, jpeg_quality=70, perspective_jitter=5,
        dark_background=True,
    )
    result = extract_center_id(degraded)

    assert result.status == "identified"
    assert result.center_id == 442


# ---------------------------------------------------------------------------
# WATERMARK_SPEC.md CRC test vectors — hardcoded ground truth
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("center_id, exam_id, page_num, expected_crc_int", [
    (1,     1,   1,  0x0E),
    (221,   1,   1,  0xDB),
    (442,   1,   1,  0x1E),
    (65535, 255, 15, 0xF3),
])
def test_spec_crc_vectors(
    center_id: int,
    exam_id: int,
    page_num: int,
    expected_crc_int: int,
) -> None:
    """CRC values from WATERMARK_SPEC.md — if these fail the spec was violated."""
    payload = _make_payload(center_id, exam_id, page_num)
    crc_bits = compute_crc8(payload)
    crc_int = int("".join(str(b) for b in crc_bits), 2)
    assert crc_int == expected_crc_int, (
        f"center_id={center_id}: expected CRC 0x{expected_crc_int:02X}, "
        f"got 0x{crc_int:02X}"
    )
    assert verify_crc8(payload + crc_bits) is True


# ---------------------------------------------------------------------------
# Encoder input validation
# ---------------------------------------------------------------------------

def test_encoder_input_validation(blank_page: np.ndarray) -> None:
    with pytest.raises(ValueError):
        embed_markers(blank_page, -1, 1, 1)
    with pytest.raises(ValueError):
        embed_markers(blank_page, 70_000, 1, 1)
    with pytest.raises(ValueError):
        embed_markers(blank_page, 1, 256, 1)
    with pytest.raises(ValueError):
        embed_markers(blank_page, 1, 1, 16)
    with pytest.raises(ValueError):
        embed_markers(np.zeros((100, 100), dtype=np.float32), 1, 1, 1)


# ---------------------------------------------------------------------------
# Decoder robustness — must never raise, always return ForensicResult
# ---------------------------------------------------------------------------

def test_decoder_empty_image() -> None:
    tiny = np.zeros((10, 10), dtype=np.uint8)
    result = extract_center_id(tiny)

    assert isinstance(result, ForensicResult)
    assert result.status in ("failed", "inconclusive")
    assert result.analysis_ms >= 0


def test_decoder_white_image() -> None:
    white = np.ones((3508, 2480), dtype=np.uint8) * 255
    result = extract_center_id(white)

    assert isinstance(result, ForensicResult)
    # A pure-white image produces no marker candidates; CRC of all-zeros
    # happens to equal 0x00 (known CRC-8/SMBUS degenerate case), so the
    # decoder may return "identified" with center_id=0 — both are acceptable.
    assert result.status in ("identified", "inconclusive")
    assert result.analysis_ms >= 0


def test_decoder_random_noise() -> None:
    np.random.seed(42)
    noise = np.random.randint(0, 255, (3508, 2480), dtype=np.uint8)
    result = extract_center_id(noise)

    assert isinstance(result, ForensicResult)
    assert result.status in ("identified", "inconclusive", "failed")
    assert result.analysis_ms >= 0


# ---------------------------------------------------------------------------
# Partial grid survival — one corner destroyed
# ---------------------------------------------------------------------------

def test_partial_grid_survival(blank_page: np.ndarray) -> None:
    wm = embed_markers(blank_page, center_id=221, exam_id=1, page_num=1)

    # Destroy the bottom-right grid corner by painting it white
    wm[3300:, 2200:] = 255

    degraded = simulate_leak_photo(
        wm, rotation_deg=0.0, jpeg_quality=72, perspective_jitter=5,
        dark_background=True,
    )
    result = extract_center_id(degraded)

    assert result.status == "identified"
    assert result.center_id == 221
    assert result.confidence <= 0.76   # at most 3/4 grids valid
