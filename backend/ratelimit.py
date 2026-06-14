"""Shared slowapi rate limiter.

Defined in its own module so both ``main.py`` (handler registration) and the
route modules (endpoint decoration) can import it without a circular import.
Per-IP, in-memory counters (BUGS-009: per-process, acceptable for the MVP).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter: Limiter = Limiter(key_func=get_remote_address)

# Forensic uploads are expensive (image decode + watermark extraction); cap the
# burst rate per client so a flood of uploads cannot exhaust the worker.
FORENSICS_ANALYZE_RATE: str = "10/minute"
