"""
Single source of truth for all configuration.
All other modules import from here — never read os.environ directly.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _require_env(key: str) -> str:
    """Read a required env var. Raises RuntimeError with a clear message if missing."""
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(
            f"Required environment variable {key} is not set. See README.md."
        )
    return value


def _optional_env(key: str, default: str) -> str:
    """Read an optional env var. Logs a warning when the default is used."""
    value = os.environ.get(key)
    if not value:
        logger.warning("Using default for %s: %r", key, default)
        return default
    return value


# --- Required (app will not start without these) ---
MASTER_KEY_HEX: str = _require_env("EXAMSHIELD_MASTER_KEY")
MASTER_KEY: bytes = bytes.fromhex(MASTER_KEY_HEX)

# --- Optional with defaults ---
DB_PATH: Path = Path(_optional_env("EXAMSHIELD_DB_PATH", "examshield.db"))
UPLOADS_DIR: Path = Path(
    _optional_env("EXAMSHIELD_UPLOADS_DIR", "/tmp/examshield_uploads")
)
ALLOWED_ORIGINS: list[str] = _optional_env(
    "EXAMSHIELD_ALLOWED_ORIGINS", "http://localhost:3000"
).split(",")

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# --- Upload validation constants ---
MAX_UPLOAD_BYTES: int = 15 * 1024 * 1024  # 15 MB
ALLOWED_MIMES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})

# --- Anomaly detection thresholds ---
EARLY_ACCESS_THRESHOLD_MINUTES: int = 0
RAPID_REQUEST_WINDOW_SECONDS: int = 60
RAPID_REQUEST_MAX_COUNT: int = 3

# --- App metadata ---
APP_TITLE: str = "ExamShield"
APP_VERSION: str = "0.1.0"
