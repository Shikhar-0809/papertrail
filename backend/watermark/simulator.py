"""
Leak-photo simulator for watermark testing and demo generation.

Applies a realistic print-then-photograph-then-WhatsApp degradation pipeline.
Used ONLY in tests and demo generation — never imported by production paths.

For reproducible demo videos, pass fixed ``rotation_deg`` and ``jpeg_quality``
values; those two parameters are the only sources of randomness.
For random-mode reproducibility, call ``np.random.seed(N)`` before invoking
this function (legacy numpy RNG is intentional so callers can seed globally).
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — degradation parameters
# ---------------------------------------------------------------------------

_BLUR_KERNEL: tuple[int, int] = (3, 3)
_BLUR_SIGMA: float = 0.8

_ROTATION_MIN: float = -5.0
_ROTATION_MAX: float = 5.0

_JPEG_QUALITY_MIN: int = 65
_JPEG_QUALITY_MAX: int = 75

_DARK_BG_PAD: int = 100   # pixels of dark border added on each side
_DARK_BG_FILL: int = 40   # grayscale intensity of the dark canvas


# ---------------------------------------------------------------------------
# Private step helpers
# ---------------------------------------------------------------------------

def _white_fill(image: np.ndarray) -> int | tuple[int, int, int]:
    """Return the appropriate white border value for the image channel count."""
    return 255 if image.ndim == 2 else (255, 255, 255)


def _step_dark_background(image: np.ndarray) -> np.ndarray:
    """Place *image* onto a dark canvas so the page boundary is detectable."""
    pad = _DARK_BG_PAD
    canvas = np.full(
        (image.shape[0] + 2 * pad, image.shape[1] + 2 * pad),
        _DARK_BG_FILL,
        dtype=np.uint8,
    )
    canvas[pad:pad + image.shape[0], pad:pad + image.shape[1]] = image
    return canvas


def _step_blur(image: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(image, _BLUR_KERNEL, _BLUR_SIGMA)


def _step_noise(image: np.ndarray, noise_std: float) -> np.ndarray:
    noise = np.random.normal(0.0, noise_std, image.shape).astype(np.float32)
    return np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def _step_rotation(image: np.ndarray, angle: float, fill: int = 255) -> np.ndarray:
    h, w = image.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    return cv2.warpAffine(
        image, M, (w, h),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=_DARK_BG_FILL,
    )


def _step_perspective(image: np.ndarray, jitter: int, fill: int = 255) -> np.ndarray:
    h, w = image.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    offsets = np.random.randint(-jitter, jitter + 1, (4, 2)).astype(np.float32)
    dst = src + offsets
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(
        image, M, (w, h),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=fill,
    )


def _step_jpeg(image: np.ndarray, quality: int) -> np.ndarray:
    _, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)


def _step_to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image.astype(np.uint8)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def simulate_leak_photo(
    image: np.ndarray,
    rotation_deg: float | None = None,
    jpeg_quality: int | None = None,
    noise_std: float = 8.0,
    perspective_jitter: int = 30,
    dark_background: bool = True,
) -> np.ndarray:
    """Simulate the print → photograph → WhatsApp degradation pipeline.

    Applies exactly 6 degradations in spec-mandated order. Passing fixed
    ``rotation_deg`` and ``jpeg_quality`` values makes output deterministic.

    Args:
        image:              Input exam page, uint8 (grayscale or BGR).
        rotation_deg:       Rotation in degrees. None → uniform(-5, 5).
        jpeg_quality:       JPEG quality 1-100. None → uniform(65, 75).
        noise_std:          Gaussian noise standard deviation (default 8.0).
        perspective_jitter: Max pixel jitter per corner (default 30).
        dark_background:    When True (default), place the page on a dark canvas
                            before degradation so the decoder's page-boundary
                            detection can find the white page after rotation.
                            Set False for legacy behaviour (no canvas).

    Returns:
        Degraded grayscale uint8 ndarray.
    """
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8:
        raise ValueError("image must be a uint8 numpy ndarray")

    angle: float = (
        float(np.random.uniform(_ROTATION_MIN, _ROTATION_MAX))
        if rotation_deg is None
        else rotation_deg
    )
    quality: int = (
        int(np.random.uniform(_JPEG_QUALITY_MIN, _JPEG_QUALITY_MAX))
        if jpeg_quality is None
        else jpeg_quality
    )

    logger.debug(
        "simulate_leak_photo: rotation=%.2f quality=%d noise_std=%.1f jitter=%d dark_bg=%s",
        angle, quality, noise_std, perspective_jitter, dark_background,
    )

    border_fill: int = _DARK_BG_FILL if dark_background else 255
    img = _step_dark_background(image) if dark_background else image.copy()
    img = _step_blur(img)                                    # Step 1
    img = _step_noise(img, noise_std)                        # Step 2
    img = _step_rotation(img, angle, fill=border_fill)       # Step 3
    img = _step_perspective(img, perspective_jitter,
                            fill=border_fill)                 # Step 4
    img = _step_jpeg(img, quality)                           # Step 5
    return _step_to_gray(img)                                # Step 6
