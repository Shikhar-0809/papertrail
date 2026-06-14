"""Audit routes: read-only access to audit_log.

Routes query audit_log directly — there is no audit_service by design.
The log is append-only from services; routes only SELECT from it.
All SQL uses parameterized queries (S-003).
"""

import logging

from fastapi import APIRouter

from backend.database import get_db

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
    where_parts: list[str] = []
    params: list = []
    if exam_id:
        where_parts.append("exam_id = ?")
        params.append(exam_id)
    if center_id:
        where_parts.append("center_id = ?")
        params.append(center_id)
    if severity:
        where_parts.append("severity = ?")
        params.append(severity)
    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
    async with get_db() as db:
        count_cur = await db.execute(
            "SELECT COUNT(*) FROM audit_log" + where_sql, params
        )
        total = (await count_cur.fetchone())[0]
        cur = await db.execute(
            "SELECT * FROM audit_log" + where_sql + " ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        events = [dict(r) for r in await cur.fetchall()]
    return {"events": events, "total": total, "limit": limit, "offset": offset}


@router.get("/alerts")
async def get_alerts() -> dict:
    async with get_db() as db:
        cur = await db.execute(
            "SELECT * FROM audit_log"
            " WHERE severity IN ('HIGH','CRITICAL')"
            " ORDER BY timestamp DESC"
        )
        alerts = [dict(r) for r in await cur.fetchall()]
    return {"alerts": alerts, "count": len(alerts)}
