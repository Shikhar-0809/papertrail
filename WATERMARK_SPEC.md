# Watermark Specification

## Purpose

This document is the formal contract between `watermark/encoder.py` and `watermark/decoder.py`. Both files must be implemented exactly against this spec. If this spec and the code ever disagree, the spec wins — fix the code.

Cursor must read this entire document before generating encoder.py, decoder.py, crc.py, or simulator.py.

---

## Bit Layout (36 bits total)

```
Bit positions (0-indexed, MSB first within each field):

Bits  0–15  : center_id   (16 bits, unsigned, max 65535)
Bits 16–23  : exam_id     (8 bits,  unsigned, max 255)
Bits 24–27  : page_num    (4 bits,  unsigned, max 15)
Bits 28–35  : CRC-8       (8 bits,  computed over bits 0–27)

Total: 36 bits
```

### Encoding Example

```
center_id = 221  → binary (16 bit): 0000000011011101
exam_id   = 1    → binary (8 bit):  00000001
page_num  = 1    → binary (4 bit):  0001

Concatenated (28 bits): 0000000011011101 00000001 0001
CRC-8 of above         : computed value, appended as 8 bits

Full 36-bit sequence:
0000000011011101 00000001 0001 [8-bit CRC]
```

---

## CRC-8 Algorithm

Polynomial: 0x07 (CRC-8/SMBUS standard)
Initial value: 0x00
No reflection, no final XOR.

```python
def compute_crc8(bits: list[int]) -> list[int]:
    """
    Input: list of 28 ints (each 0 or 1), MSB first
    Output: list of 8 ints (each 0 or 1), the CRC-8 checksum
    """
    # Pack bits into bytes for CRC computation
    # Pad to nearest byte boundary (28 bits → 4 bytes, pad with zeros)
    padded = bits + [0] * (32 - len(bits))  # 32 bits = 4 bytes
    
    crc = 0x00
    for byte_idx in range(4):
        byte_val = 0
        for bit_idx in range(8):
            byte_val = (byte_val << 1) | padded[byte_idx * 8 + bit_idx]
        crc ^= byte_val
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x07
            else:
                crc <<= 1
            crc &= 0xFF
    
    # Convert CRC byte back to 8 bits
    return [(crc >> (7 - i)) & 1 for i in range(8)]
```

### Test Vectors (Verify Implementation)

```
center_id=1,   exam_id=1, page_num=1  → bits[0:28] = 0000000000000001 00000001 0001
center_id=221, exam_id=1, page_num=1  → bits[0:28] = 0000000011011101 00000001 0001
center_id=442, exam_id=1, page_num=1  → bits[0:28] = 0000000110111010 00000001 0001
center_id=65535, exam_id=255, page_num=15 → bits[0:28] = 1111111111111111 11111111 1111
```

Compute the CRC for each and hard-code expected values in `tests/test_watermark_roundtrip.py`. The test must verify that:
1. `encode → decode` returns the original center_id for all 4 test vectors
2. Flipping any single bit in positions 0-27 causes CRC verification to fail
3. Flipping any bit in positions 28-35 (the CRC itself) causes verification to fail

---

## Marker Physical Dimensions

```
Marker type    : Solid filled square (NOT circle — rectangles are easier for findContours)
Marker size    : 6 × 6 pixels at image resolution
Marker color   : RGB(180, 180, 180) — mid-gray
                 On white paper (255,255,255) this is clearly detectable
                 but not visually prominent in margin whitespace
Background     : White (255, 255, 255)
```

---

## Grid Layout

```
Grid dimensions : 6 columns × 6 rows = 36 positions
Cell spacing    : 20 pixels center-to-center (between marker centers)
Total grid area : (6-1)*20 + 6 = 106 pixels wide, 106 pixels tall

Bit-to-position mapping (row-major, left-to-right, top-to-bottom):
  Position (row=0, col=0) = bit 0  (MSB of center_id)
  Position (row=0, col=1) = bit 1
  ...
  Position (row=0, col=5) = bit 5
  Position (row=1, col=0) = bit 6
  ...
  Position (row=5, col=5) = bit 35 (LSB of CRC-8)

Marker present (filled square) = bit value 1
Marker absent  (empty space)   = bit value 0
```

---

## Placement on Page

The grid is placed in all 4 margin corners for redundancy. If a photo crops out some corners, the remaining corners still contain enough data.

```
Page assumed size: 2480 × 3508 pixels (A4 at 300 DPI)
Margin offset    : 40 pixels from page edge to nearest corner of grid

Placement coordinates (top-left corner of grid):
  TOP-LEFT     : x=40,          y=40
  TOP-RIGHT    : x=2480-40-106, y=40
  BOTTOM-LEFT  : x=40,          y=3508-40-106
  BOTTOM-RIGHT : x=2480-40-106, y=3508-40-106
```

### Encoder Must

1. Draw all 4 grids on the image
2. Only draw markers for bit=1 positions (bit=0 positions remain white)
3. Use `cv2.rectangle()` or PIL `ImageDraw.rectangle()` for solid square markers
4. Not modify any pixel outside the 4 defined grid areas

---

## Extraction Pipeline (decoder.py)

Steps in exact order. Do not reorder.

```
Step 1: Load image
  - Input may be grayscale or color
  - Convert to grayscale immediately: cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
  - If already grayscale, no-op

Step 2: Page boundary detection
  - Apply Gaussian blur: cv2.GaussianBlur(gray, (5,5), 0)
  - Threshold: cv2.threshold(blurred, 200, 255, cv2.THRESH_BINARY_INV)
  - Find contours: cv2.findContours(...)
  - Find the largest contour by area — this is the page boundary
  - If no large contour found (page fills frame), skip to Step 3

Step 3: Perspective correction
  - If page boundary found in Step 2:
    - Approximate contour to quadrilateral: cv2.approxPolyDP(...)
    - If 4 corners found: apply cv2.getPerspectiveTransform + cv2.warpPerspective
    - Target size: 2480 × 3508 (canonical A4)
  - If no boundary or not 4 corners: proceed with original image, log warning

Step 4: Adaptive threshold for dot detection
  - cv2.adaptiveThreshold(
        image, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=15,
        C=8
    )
  - This isolates dark marks on white background

Step 5: Find square marker candidates
  - cv2.findContours on thresholded image
  - Filter contours by:
    - Area: between 20 and 60 pixels (6×6=36, allow ±40% for degradation)
    - Aspect ratio: width/height between 0.5 and 2.0 (squares ± distortion)
  - These are candidate marker locations

Step 6: Grid detection
  - For each of 4 expected grid locations (corners of page):
    - Define search region: 200×200 pixel area around expected corner
    - Filter candidates to those within search region
    - Attempt to fit candidates to a 6×6 grid with 20px spacing (allow ±4px tolerance)
    - If ≥18 of 36 positions can be determined → valid grid found

Step 7: Bit extraction per grid
  - For each valid grid:
    - For each of 36 positions:
      - Check if a marker exists at that position (candidate within 8px of expected location)
      - Marker present → bit = 1
      - Marker absent → bit = 0
    - Extract 36-bit sequence

Step 8: CRC verification per grid
  - Take bits[0:28], compute CRC-8
  - Compare to bits[28:36]
  - If match: grid is valid, decode center_id/exam_id/page_num
  - If no match: grid is invalid (noise), discard

Step 9: Aggregate results
  - Collect all valid (CRC-verified) grids
  - If 0 valid grids: return status="inconclusive"
  - If ≥1 valid grid: take majority vote on center_id
    - All valid grids should agree (same paper = same center_id)
    - If they disagree: return status="inconclusive" (should never happen in practice)
  - confidence = valid_grids / 4.0

Step 10: Return ForensicResult
```

---

## ForensicResult Object

```python
@dataclass
class ForensicResult:
    status: str          # "identified" | "inconclusive" | "failed"
    center_id: int | None
    exam_id: int | None
    page_num: int | None
    confidence: float    # 0.0 to 1.0
    grids_detected: int  # 0–4 grids found in image
    grids_valid: int     # grids that passed CRC
    raw_bits: str | None # e.g. "0000000011011101..."
    analysis_ms: int     # processing time in milliseconds
    error: str | None    # if status="failed", human-readable reason
```

---

## Simulator Specification (simulator.py)

`simulate_leak_photo()` must apply degradations in exactly this order:

```python
def simulate_leak_photo(
    image: np.ndarray,
    rotation_deg: float = None,   # None = random uniform(-5, 5)
    jpeg_quality: int = None,     # None = random uniform(65, 75)
    noise_std: float = 8.0,
    perspective_jitter: int = 30
) -> np.ndarray:
    """
    Order of operations (DO NOT REORDER — order matters):
    1. Gaussian blur (kernel 3×3, sigma 0.8) — simulates print quality
    2. Gaussian noise (mean=0, std=noise_std) — simulates paper texture + camera
    3. Rotation (angle degrees, white border fill) — simulates hand-held phone
    4. Perspective warp (jitter pixels at each corner) — simulates viewing angle
    5. JPEG encode/decode at jpeg_quality — simulates WhatsApp compression
    6. Return as grayscale uint8 array
    """
```

The simulator must accept fixed parameters (not just random) so that demo images can be reproduced deterministically for the submission video.

---

## Accuracy Requirement

Before recording the demo, run `tests/test_watermark_accuracy.py`:
- 20 runs per center with random degradation parameters
- Target: ≥17/20 successful extractions (85% accuracy)
- If accuracy is below 85%:
  - First try: increase marker size to 8×8 px, re-run
  - Second try: increase marker color contrast to RGB(150,150,150), re-run
  - Third try: increase grid cell spacing to 25px, re-run
  - Document the final parameters in this file under "Tuned Parameters"
- Never fake the output to hit accuracy targets

## Tuned Parameters (Update After M1 Testing)

```
# Fill these in after running test_watermark_accuracy.py
Final marker size    : 6×6 px (or updated value)
Final marker color   : RGB(180,180,180) (or updated value)
Final grid spacing   : 20px (or updated value)
Achieved accuracy    : __/20 runs successful
Date tuned           : 
```
