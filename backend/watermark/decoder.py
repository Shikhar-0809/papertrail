"""
Public interface for the watermark decoder.

Orchestrates the full 10-step extraction pipeline defined in WATERMARK_SPEC.md.
All pipeline logic lives in decoder_pipeline.py.
All data structures live in decoder_result.py.

Existing callers (e.g. forensics_service.py) import from this module unchanged.
"""

import logging

import numpy as np

from backend.watermark.decoder_pipeline import _run_pipeline
from backend.watermark.decoder_result import ExtractionFailed, ForensicResult

logger = logging.getLogger(__name__)

__all__ = ["extract_center_id", "ForensicResult", "ExtractionFailed"]


def extract_center_id(image: np.ndarray) -> ForensicResult:
    """
    Public entry point. Orchestrates the full 10-step extraction pipeline.
    See decoder_pipeline.py for implementation details.
    See WATERMARK_SPEC.md for the pipeline specification.
    """
    return _run_pipeline(image)
