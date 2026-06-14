"""Vault routes: key release and vault status."""

import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.services.vault_service import (
    KeyNotYetAvailable,
    VaultEntryNotFound,
    get_vault_status,
    release_key,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vault", tags=["vault"])

_UUID_RE = re.compile(r"^[a-f0-9\-]{36}$")
_CODE_RE = re.compile(r"^[A-Z0-9_-]{3,50}$")


class KeyReleasedResponse(BaseModel):
    key: str
    algorithm: str
    released_at: str


@router.get("/release/{exam_id}/{center_id}", response_model=KeyReleasedResponse)
async def get_release_key(
    exam_id: str, center_id: str, request: Request
) -> KeyReleasedResponse:
    if not _UUID_RE.match(exam_id):
        return JSONResponse(status_code=400, content={"error": "Invalid exam_id format", "code": "VALIDATION_ERROR"})
    if not _CODE_RE.match(center_id):
        return JSONResponse(status_code=400, content={"error": "Invalid center_id format", "code": "VALIDATION_ERROR"})
    ip = request.client.host if request.client else "unknown"
    try:
        result = await release_key(exam_id, center_id, ip)
        return KeyReleasedResponse(**result)
    except KeyNotYetAvailable as exc:
        return JSONResponse(status_code=403, content={
            "error": "Decryption key not yet available",
            "code": "KEY_NOT_YET_AVAILABLE",
            "release_at": exc.release_at.isoformat(),
            "minutes_remaining": exc.minutes_remaining,
        })
    except VaultEntryNotFound:
        return JSONResponse(status_code=404, content={"error": "Vault entry not found", "code": "NOT_FOUND"})


@router.get("/status/{exam_id}")
async def get_vault_status_endpoint(exam_id: str) -> dict:  # type: ignore[return]
    result = await get_vault_status(exam_id)
    if result is None:
        return JSONResponse(status_code=404, content={"error": "Exam not found", "code": "NOT_FOUND"})
    return result
