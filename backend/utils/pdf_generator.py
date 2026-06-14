"""Generates a minimal A4 exam paper page as a numpy uint8 grayscale array.

Pure computation — no I/O, no HTTP, no database access.
"""

import numpy as np

_PAGE_W: int = 2480  # A4 at 300 DPI
_PAGE_H: int = 3508


def generate_page() -> np.ndarray:
    """Return a white A4 grayscale page (3508 × 2480, uint8)."""
    return np.full((_PAGE_H, _PAGE_W), 255, dtype=np.uint8)
