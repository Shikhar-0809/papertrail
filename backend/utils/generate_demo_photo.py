"""Demo/dev tool: generate a self-verified "leaked" watermarked exam photo.

NOT a production code path. As an explicit dev tool it is allowed to call
encoder/, simulator/ and decoder/ directly (ARCHITECTURE.md). It embeds a
watermark, simulates print→photo→WhatsApp degradation, saves the image, then
re-decodes the saved file to PROVE the watermark survives before declaring
success. ``print`` is intentional here — this is a CLI tool, not backend code.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

# Allow running directly as `python backend/utils/generate_demo_photo.py`
# (not just `python -m ...`) by putting the repo root on sys.path first.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.watermark.decoder import ForensicResult, extract_center_id  # noqa: E402
from backend.watermark.encoder import embed_markers  # noqa: E402
from backend.watermark.simulator import simulate_leak_photo  # noqa: E402

_PAGE_W: int = 2480
_PAGE_H: int = 3508
_EXAM_ID: int = 1
_PAGE_NUM: int = 1
_DEFAULT_OUTPUT: str = "demo/test_photos/leaked_center_221.jpg"
_SEED: int = 7  # deterministic noise/jitter so the demo image is reproducible


def _build_photo(center_id: int, rotation: float, quality: int) -> np.ndarray:
    """Create a white A4 page, embed the watermark, and degrade it."""
    page = np.full((_PAGE_H, _PAGE_W), 255, dtype=np.uint8)
    watermarked = embed_markers(page, center_id, _EXAM_ID, _PAGE_NUM)
    np.random.seed(_SEED)
    return simulate_leak_photo(watermarked, rotation_deg=rotation, jpeg_quality=quality)


def _verify_saved(path: Path, expected_center: int) -> ForensicResult:
    """Re-read the saved file and confirm the watermark decodes correctly."""
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        print(f"ERROR: could not read the saved image at {path}")
        sys.exit(1)
    result = extract_center_id(image)
    if result.status != "identified" or result.center_id != expected_center:
        print("!" * 64)
        print(f"VERIFICATION FAILED: expected center {expected_center} 'identified', "
              f"got center={result.center_id} status={result.status} "
              f"confidence={result.confidence:.1%}")
        print("!" * 64)
        sys.exit(1)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a self-verifying demo leak photo")
    parser.add_argument("--center-id", type=int, default=221)
    parser.add_argument("--rotation", type=float, default=3.0)
    parser.add_argument("--quality", type=int, default=70)
    parser.add_argument("--output", type=str, default=_DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    photo = _build_photo(args.center_id, args.rotation, args.quality)
    cv2.imwrite(str(output), photo)

    result = _verify_saved(output, args.center_id)
    print(f"Demo photo saved and verified: {output}")
    print(f"  center_id   : {result.center_id}")
    print(f"  confidence  : {result.confidence:.1%}")
    print(f"  grids_valid : {result.grids_valid}/{result.grids_detected}")
    print(f"  analysis_ms : {result.analysis_ms}")


if __name__ == "__main__":
    main()
