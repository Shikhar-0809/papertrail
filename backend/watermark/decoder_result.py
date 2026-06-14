"""
Data structures, result types, and result-building helpers for the watermark
decoder.  No I/O, no CV, no HTTP.  Pure data and computation.
"""

import logging
import time
from collections import Counter
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger(__name__)

# Sentinel: all-zeros 36-bit sequence is a degenerate CRC-8/SMBUS valid codeword
# (init=0x00 means CRC([0]*36) == [0]*8). Skip grids that produce this pattern.
_ALL_ZEROS_SENTINEL: Final[list[int]] = [0] * 36


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

@dataclass
class ForensicResult:
    status: str           # "identified" | "inconclusive" | "failed"
    center_id: int | None
    exam_id: int | None
    page_num: int | None
    confidence: float     # 0.0 to 1.0
    grids_detected: int   # 0–4 grids found
    grids_valid: int      # grids that passed CRC
    raw_bits: str | None  # e.g. "0000000011011101..."
    analysis_ms: int      # processing time in milliseconds
    error: str | None     # human-readable reason if status="failed"


class ExtractionFailed(Exception):
    pass


# ---------------------------------------------------------------------------
# Steps 9–10 — Aggregate + build result
# ---------------------------------------------------------------------------

def _failed_result(start: float, error: str) -> ForensicResult:
    return ForensicResult(
        status="failed", center_id=None, exam_id=None, page_num=None,
        confidence=0.0, grids_detected=0, grids_valid=0, raw_bits=None,
        analysis_ms=int((time.monotonic() - start) * 1000), error=error,
    )


def _build_result(
    start: float,
    grids_detected: int,
    valid_decoded: list[tuple[int, int, int]],
    raw_bits: str | None,
) -> ForensicResult:
    elapsed = int((time.monotonic() - start) * 1000)
    grids_valid = len(valid_decoded)
    confidence = grids_valid / 4.0

    if grids_valid == 0:
        return ForensicResult(
            status="inconclusive", center_id=None, exam_id=None, page_num=None,
            confidence=confidence, grids_detected=grids_detected, grids_valid=0,
            raw_bits=raw_bits, analysis_ms=elapsed, error=None,
        )

    vote: Counter[int] = Counter(cid for cid, _, _ in valid_decoded)
    top_cid, top_count = vote.most_common(1)[0]
    if top_count < grids_valid:
        logger.warning("Grid center_id disagreement: %s", dict(vote))
        return ForensicResult(
            status="inconclusive", center_id=None, exam_id=None, page_num=None,
            confidence=confidence, grids_detected=grids_detected, grids_valid=grids_valid,
            raw_bits=raw_bits, analysis_ms=elapsed, error=None,
        )

    _, exam_id, page_num = next(r for r in valid_decoded if r[0] == top_cid)
    return ForensicResult(
        status="identified", center_id=top_cid, exam_id=exam_id, page_num=page_num,
        confidence=confidence, grids_detected=grids_detected, grids_valid=grids_valid,
        raw_bits=raw_bits, analysis_ms=elapsed, error=None,
    )
