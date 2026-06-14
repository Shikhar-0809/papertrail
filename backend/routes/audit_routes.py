"""Audit routes: read-only access to audit_log via audit_service."""

import logging

from fastapi import APIRouter

from backend.services import audit_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/log")
async def get_audit_log(
    exam_id: str | None = None,
    center_id: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    limit = min(limit, 200)
    events, total = await audit_service.get_audit_log(
        exam_id, center_id, severity, limit, offset,
    )
    return {"events": events, "total": total, "limit": limit, "offset": offset}


@router.get("/alerts")
async def get_alerts() -> dict:
    alerts = await audit_service.get_alerts()
    return {"alerts": alerts, "count": len(alerts)}
