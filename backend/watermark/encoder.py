"""
Watermark encoder: embeds a 36-bit forensic marker grid into all 4 corners of
an exam page image.

Spec reference: WATERMARK_SPEC.md — Bit Layout, Marker Physical Dimensions,
Grid Layout, Placement on Page.

This module is pure computation: no I/O, no HTTP, no database access.
"""

import logging
from typing import Final

import numpy as np

from backend.watermark.crc import compute_crc8

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Grid geometry — WATERMARK_SPEC.md "Grid Layout" / "Marker Physical Dimensions"
# ---------------------------------------------------------------------------

GRID_ROWS: Final[int] = 6
GRID_COLS: Final[int] = 6
GRID_SPACING_PX: Final[int] = 20          # center-to-center distance
MARKER_SIZE_PX: Final[int] = 6            # solid square side length in pixels
MARKER_COLOR_GRAY: Final[int] = 180       # grayscale value (same as RGB 180)
MARKER_COLOR_BGR: Final[tuple[int, int, int]] = (180, 180, 180)

# ---------------------------------------------------------------------------
# Page dimensions & corner placement — WATERMARK_SPEC.md "Placement on Page"
# ---------------------------------------------------------------------------

_PAGE_W: Final[int] = 2480
_PAGE_H: Final[int] = 3508
_MARGIN: Final[int] = 40
# Total grid footprint: (cols-1)*spacing + marker_size = 5*20 + 6 = 106 px
_GRID_AREA: Final[int] = (GRID_COLS - 1) * GRID_SPACING_PX + MARKER_SIZE_PX

# (x, y) top-left corner of each grid, exactly as listed in the spec
_GRID_CORNERS: Final[list[tuple[int, int]]] = [
    (_MARGIN,                          _MARGIN),                           # TOP-LEFT
    (_PAGE_W - _MARGIN - _GRID_AREA,   _MARGIN),                           # TOP-RIGHT
    (_MARGIN,                          _PAGE_H - _MARGIN - _GRID_AREA),    # BOTTOM-LEFT
    (_PAGE_W - _MARGIN - _GRID_AREA,   _PAGE_H - _MARGIN - _GRID_AREA),    # BOTTOM-RIGHT
]

# ---------------------------------------------------------------------------
# Field widths
# ---------------------------------------------------------------------------

_CENTER_ID_BITS: Final[int] = 16
_EXAM_ID_BITS: Final[int] = 8
_PAGE_NUM_BITS: Final[int] = 4
_DATA_BITS: Final[int] = _CENTER_ID_BITS + _EXAM_ID_BITS + _PAGE_NUM_BITS  # 28
_TOTAL_BITS: Final[int] = _DATA_BITS + 8                                    # 36

# ---------------------------------------------------------------------------
# Validation ranges
# ---------------------------------------------------------------------------

_CENTER_ID_MAX: Final[int] = (1 << _CENTER_ID_BITS) - 1   # 65535
_EXAM_ID_MAX: Final[int] = (1 << _EXAM_ID_BITS) - 1       # 255
_PAGE_NUM_MAX: Final[int] = (1 << _PAGE_NUM_BITS) - 1     # 15


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _int_to_bits(value: int, width: int) -> list[int]:
    """Convert an unsigned integer to a fixed-width MSB-first bit list."""
    return [(value >> (width - 1 - i)) & 1 for i in range(width)]


def _draw_grid(
    image: np.ndarray,
    top_left_x: int,
    top_left_y: int,
    bits: list[int],
) -> None:
    """Draw one 6×6 marker grid onto *image* at the given top-left corner.

    Modifies *image* in-place. Skips positions where bit=0 (leave white).
    Works for both grayscale (ndim==2) and BGR color (ndim==3) images.
    """
    color: int | tuple[int, int, int] = (
        MARKER_COLOR_GRAY if image.ndim == 2 else MARKER_COLOR_BGR
    )
    for bit_idx, bit_val in enumerate(bits):
        if bit_val == 0:
            continue
        row, col = divmod(bit_idx, GRID_COLS)
        x0 = top_left_x + col * GRID_SPACING_PX
        y0 = top_left_y + row * GRID_SPACING_PX
        image[y0 : y0 + MARKER_SIZE_PX, x0 : x0 + MARKER_SIZE_PX] = color


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed_markers(
    image: np.ndarray,
    center_id: int,
    exam_id: int,
    page_num: int,
) -> np.ndarray:
    """Embed a 36-bit forensic watermark grid into all 4 corners of *image*.

    Builds a 36-bit sequence:
      bits  0–15 : center_id  (16 bits, MSB first)
      bits 16–23 : exam_id    (8 bits,  MSB first)
      bits 24–27 : page_num   (4 bits,  MSB first)
      bits 28–35 : CRC-8      (8 bits,  computed over bits 0–27)

    Then draws a 6×6 grid of 6×6-pixel gray markers in each of the 4 page
    corners. Marker present = bit 1; marker absent = bit 0 (no pixel change).

    Args:
        image:     uint8 numpy array (grayscale HxW or BGR HxWx3).
        center_id: Exam center identifier, 0–65535.
        exam_id:   Exam identifier, 0–255.
        page_num:  Page number, 0–15.

    Returns:
        A copy of *image* with the watermark grids drawn in all 4 corners.

    Raises:
        ValueError: If any argument is out of range or image has wrong type/dtype.
    """
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8:
        raise ValueError("image must be a numpy ndarray with dtype uint8")
    if not (0 <= center_id <= _CENTER_ID_MAX):
        raise ValueError(f"center_id must be 0–{_CENTER_ID_MAX}, got {center_id}")
    if not (0 <= exam_id <= _EXAM_ID_MAX):
        raise ValueError(f"exam_id must be 0–{_EXAM_ID_MAX}, got {exam_id}")
    if not (0 <= page_num <= _PAGE_NUM_MAX):
        raise ValueError(f"page_num must be 0–{_PAGE_NUM_MAX}, got {page_num}")

    data_bits: list[int] = (
        _int_to_bits(center_id, _CENTER_ID_BITS)
        + _int_to_bits(exam_id, _EXAM_ID_BITS)
        + _int_to_bits(page_num, _PAGE_NUM_BITS)
    )
    bits_36: list[int] = data_bits + compute_crc8(data_bits)

    output: np.ndarray = image.copy()
    for corner_x, corner_y in _GRID_CORNERS:
        _draw_grid(output, corner_x, corner_y, bits_36)

    logger.info(
        "embed_markers: center_id=%d exam_id=%d page_num=%d",
        center_id, exam_id, page_num,
    )
    return output
