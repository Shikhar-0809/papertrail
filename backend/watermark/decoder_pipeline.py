"""
Full 10-step watermark extraction pipeline.
See WATERMARK_SPEC.md for the algorithm specification.
Pure computation — no I/O, no database, no HTTP.
"""

import logging
import time
from typing import Final

import cv2
import numpy as np

from backend.watermark.crc import verify_crc8
from backend.watermark.decoder_result import (
    ForensicResult,
    _ALL_ZEROS_SENTINEL,
    _build_result,
    _failed_result,
)

logger = logging.getLogger(__name__)

# Grid geometry — must match encoder constants exactly
GRID_ROWS: Final[int] = 6
GRID_COLS: Final[int] = 6
GRID_SPACING_PX: Final[int] = 20
MARKER_SIZE_PX: Final[int] = 6
_GRID_AREA: Final[int] = (GRID_COLS - 1) * GRID_SPACING_PX + MARKER_SIZE_PX  # 106

_PAGE_W: Final[int] = 2480
_PAGE_H: Final[int] = 3508
_MARGIN: Final[int] = 40

_GRID_CORNERS: Final[list[tuple[int, int]]] = [
    (_MARGIN,                        _MARGIN),
    (_PAGE_W - _MARGIN - _GRID_AREA, _MARGIN),
    (_MARGIN,                        _PAGE_H - _MARGIN - _GRID_AREA),
    (_PAGE_W - _MARGIN - _GRID_AREA, _PAGE_H - _MARGIN - _GRID_AREA),
]

# Detection thresholds
AREA_MIN: Final[int] = 20
AREA_MAX: Final[int] = 60
ASPECT_MIN: Final[float] = 0.5
ASPECT_MAX: Final[float] = 2.0
SEARCH_REGION_PX: Final[int] = 200
MIN_VALID_POSITIONS: Final[int] = 18
GRID_FIT_TOLERANCE_PX: Final[int] = 4
MARKER_PROXIMITY_PX: Final[int] = 8

_BLUR_KERNEL: Final[tuple[int, int]] = (5, 5)
_PAGE_THRESH_VAL: Final[int] = 200
_MIN_PAGE_AREA: Final[int] = 50_000
_AT_BLOCK_SIZE: Final[int] = 15
_AT_C: Final[int] = 8
_SEARCH_MARGIN: Final[int] = (SEARCH_REGION_PX - _GRID_AREA) // 2  # 47

# Bit field offsets
_CENTER_ID_BITS: Final[int] = 16
_EXAM_ID_BITS: Final[int] = 8
_PAGE_NUM_BITS: Final[int] = 4

def _to_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _detect_page_boundary(gray: np.ndarray) -> np.ndarray | None:
    blurred = cv2.GaussianBlur(gray, _BLUR_KERNEL, 0)
    _, thresh = cv2.threshold(blurred, _PAGE_THRESH_VAL, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < _MIN_PAGE_AREA:
        return None
    return largest


def _sort_corners(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).ravel()   # y - x per point
    rect[0] = pts[np.argmin(s)]           # TL: smallest x+y
    rect[2] = pts[np.argmax(s)]           # BR: largest x+y
    rect[1] = pts[np.argmin(diff)]        # TR: most negative y-x
    rect[3] = pts[np.argmax(diff)]        # BL: most positive y-x
    return rect


def _apply_perspective(gray: np.ndarray, contour: np.ndarray) -> np.ndarray:
    epsilon = 0.02 * cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    if len(approx) != 4:
        logger.warning("Perspective skip: %d corners found (need 4)", len(approx))
        return gray
    src = _sort_corners(approx.reshape(4, 2).astype(np.float32))
    dst = np.float32([[0, 0], [_PAGE_W, 0], [_PAGE_W, _PAGE_H], [0, _PAGE_H]])
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(gray, M, (_PAGE_W, _PAGE_H))


def _adaptive_threshold(image: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(
        image, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        _AT_BLOCK_SIZE, _AT_C,
    )


def _find_marker_candidates(thresh: np.ndarray) -> list[tuple[int, int]]:
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[int, int]] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if not (AREA_MIN <= area <= AREA_MAX):
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        if h == 0:
            continue
        if not (ASPECT_MIN <= w / h <= ASPECT_MAX):
            continue
        candidates.append((x + w // 2, y + h // 2))
    return candidates


def _candidates_in_region(
    candidates: list[tuple[int, int]],
    corner_x: int,
    corner_y: int,
) -> list[tuple[int, int]]:
    x_lo = corner_x - _SEARCH_MARGIN
    x_hi = corner_x + _GRID_AREA + _SEARCH_MARGIN
    y_lo = corner_y - _SEARCH_MARGIN
    y_hi = corner_y + _GRID_AREA + _SEARCH_MARGIN
    return [(cx, cy) for cx, cy in candidates if x_lo <= cx <= x_hi and y_lo <= cy <= y_hi]


def _expected_center(corner_x: int, corner_y: int, row: int, col: int) -> tuple[int, int]:
    half = MARKER_SIZE_PX // 2
    return (corner_x + col * GRID_SPACING_PX + half,
            corner_y + row * GRID_SPACING_PX + half)


def _count_inbounds_positions(
    corner_x: int,
    corner_y: int,
    img_h: int,
    img_w: int,
) -> int:
    """Count grid positions in-bounds (determinable as 0 or 1)."""
    count = 0
    for bit_idx in range(GRID_ROWS * GRID_COLS):
        row, col = divmod(bit_idx, GRID_COLS)
        ex, ey = _expected_center(corner_x, corner_y, row, col)
        if 0 <= ey < img_h and 0 <= ex < img_w:
            count += 1
    return count


def _extract_grid_bits(
    region_cands: list[tuple[int, int]],
    corner_x: int,
    corner_y: int,
) -> list[int]:
    bits: list[int] = []
    for bit_idx in range(GRID_ROWS * GRID_COLS):
        row, col = divmod(bit_idx, GRID_COLS)
        ex, ey = _expected_center(corner_x, corner_y, row, col)
        bit = int(any(
            abs(cx - ex) <= MARKER_PROXIMITY_PX and abs(cy - ey) <= MARKER_PROXIMITY_PX
            for cx, cy in region_cands
        ))
        bits.append(bit)
    return bits


def _decode_payload(bits: list[int]) -> tuple[int, int, int]:
    center_id = sum(bits[i] << (15 - i) for i in range(_CENTER_ID_BITS))
    exam_id = sum(bits[_CENTER_ID_BITS + i] << (7 - i) for i in range(_EXAM_ID_BITS))
    page_num = sum(bits[24 + i] << (3 - i) for i in range(_PAGE_NUM_BITS))
    return center_id, exam_id, page_num


def _process_all_grids(
    candidates: list[tuple[int, int]],
    img_shape: tuple[int, ...],
) -> tuple[int, list[tuple[int, int, int]], str | None]:
    """Steps 6–8: detect, extract bits, and CRC-verify all 4 corners."""
    grids_detected = 0
    valid_decoded: list[tuple[int, int, int]] = []
    first_raw_bits: str | None = None
    img_h, img_w = img_shape[:2]

    for corner_x, corner_y in _GRID_CORNERS:
        if _count_inbounds_positions(corner_x, corner_y, img_h, img_w) < MIN_VALID_POSITIONS:
            continue
        grids_detected += 1
        region_cands = _candidates_in_region(candidates, corner_x, corner_y)
        # Skip corners with no marker candidates at all.  Without this guard, a
        # blank region would produce all-zero bits whose CRC-8/SMBUS value is
        # also 0x00 (init=0x00 degenerate case), causing a false CRC match.
        if not region_cands:
            continue
        bits = _extract_grid_bits(region_cands, corner_x, corner_y)
        if bits == _ALL_ZEROS_SENTINEL:
            logger.debug("Skipping all-zeros grid — degenerate CRC-8 false positive")
            continue
        if not verify_crc8(bits):
            continue
        decoded = _decode_payload(bits)
        valid_decoded.append(decoded)
        if first_raw_bits is None:
            first_raw_bits = "".join(str(b) for b in bits)

    return grids_detected, valid_decoded, first_raw_bits


def _run_pipeline(image: np.ndarray) -> ForensicResult:
    """Run the 10-step WATERMARK_SPEC.md pipeline on *image*.

    Always returns a ForensicResult (status: identified/inconclusive/failed).
    Never raises to the caller — all exceptions are caught internally.
    """
    start = time.monotonic()
    if not isinstance(image, np.ndarray) or image.size == 0:
        return _failed_result(start, "Empty or null image provided")
    try:
        gray = _to_grayscale(image)
        boundary = _detect_page_boundary(gray)
        if boundary is not None:
            gray = _apply_perspective(gray, boundary)
        thresh = _adaptive_threshold(gray)
        candidates = _find_marker_candidates(thresh)
        grids_detected, valid_decoded, raw_bits = _process_all_grids(candidates, gray.shape)
        result = _build_result(start, grids_detected, valid_decoded, raw_bits)
        logger.info(
            "extract_center_id: status=%s grids=%d/%d confidence=%.2f",
            result.status, result.grids_valid, result.grids_detected, result.confidence,
        )
        return result
    except cv2.error as e:
        logger.error("OpenCV error in extract_center_id: %s", e, exc_info=True)
        return _failed_result(start, "Image processing error")
    except Exception as e:
        logger.error("Unexpected error in extract_center_id: %s", e, exc_info=True)
        return _failed_result(start, "Unexpected processing error")
