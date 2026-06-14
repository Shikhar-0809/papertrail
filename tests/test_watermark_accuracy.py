"""
M1 milestone accuracy gate: ≥85% extraction success rate (≥17/20 runs) under
realistic random degradation parameters.

Run with: pytest tests/test_watermark_accuracy.py -v -s
The -s flag prints per-run results so you can see individual extraction outcomes.

CURRENT STATUS: FAILING (0/20) — see BUGS-010 in BUGS.md for root-cause analysis.

Root cause in brief:
  simulate_leak_photo uses random rotation uniform(±5°).  The farthest grid corner
  is ~2092 px from the image centre, so even 0.5° moves it 18 px — more than twice
  MARKER_PROXIMITY_PX=8.  The decoder's perspective-correction step is skipped
  because the test image (white page on white fill) has no visible boundary, so
  hardcoded expected positions are used on a rotated image.

Required fix: implement rotation-invariant grid search (BUGS-010 option A) or add
  a visible dark-background canvas to the simulator (BUGS-010 option B).

Do NOT lower _THRESHOLD or hardcode successful extractions.
"""

import numpy as np
import pytest

from backend.watermark.decoder import extract_center_id
from backend.watermark.encoder import embed_markers
from backend.watermark.simulator import simulate_leak_photo

_CENTER_ID = 221
_EXAM_ID = 1
_PAGE_NUM = 1
_RUNS = 20
_THRESHOLD = 17  # 85% of 20


def test_extraction_accuracy_85_percent() -> None:
    blank = np.ones((3508, 2480), dtype=np.uint8) * 255
    wm = embed_markers(blank, center_id=_CENTER_ID, exam_id=_EXAM_ID, page_num=_PAGE_NUM)

    successes = 0
    for i in range(_RUNS):
        degraded = simulate_leak_photo(wm, dark_background=True)  # random rotation_deg and jpeg_quality
        result = extract_center_id(degraded)
        ok = result.status == "identified" and result.center_id == _CENTER_ID
        if ok:
            successes += 1
        print(f"Run {i + 1:02d}/20: {result.status:<12} conf={result.confidence:.2f}  {'OK' if ok else 'FAIL'}")

    print(f"Accuracy: {successes}/20 ({100 * successes // 20}%)")
    assert successes >= _THRESHOLD, (
        f"Accuracy {successes}/20 below 85% threshold. "
        "See WATERMARK_SPEC.md tuning guidance."
    )
