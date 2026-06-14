"""Dashboard routes: aggregated statistics and event timeline.

Routes query DB directly — read-only aggregation, no business logic.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from backend.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class DashboardStatsResponse(BaseModel):
    total_exams: int
    total_centers: int
    papers_generated: int
    keys_released: int
    active_alerts: int
    forensic_analyses: int
    leaks_identified: int


async def _count(db, sql: str, params: tuple = ()) -> int:
    cur = await db.execute(sql, params)
    row = await cur.fetchone()
    return int(row[0]) if row else 0


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_stats() -> DashboardStatsResponse:
    async with get_db() as db:
        return DashboardStatsResponse(
            total_exams=await _count(db, "SELECT COUNT(*) FROM exams"),
            total_centers=await _count(db, "SELECT COUNT(*) FROM exam_centers"),
            papers_generated=await _count(
                db, "SELECT COUNT(*) FROM vault WHERE encrypted_pdf_path IS NOT NULL"
            ),
            keys_released=await _count(db, "SELECT COUNT(*) FROM vault WHERE is_released=1"),
            active_alerts=await _count(
                db, "SELECT COUNT(*) FROM audit_log WHERE severity IN ('HIGH','CRITICAL')"
            ),
            forensic_analyses=await _count(db, "SELECT COUNT(*) FROM forensic_reports"),
            leaks_identified=await _count(
                db, "SELECT COUNT(*) FROM forensic_reports WHERE status='identified'"
            ),
        )


@router.get("/timeline")
async def get_timeline() -> dict:
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, event_type, center_id, severity, human_readable, timestamp"
            " FROM audit_log ORDER BY timestamp DESC LIMIT 50"
        )
        events = [dict(r) for r in await cur.fetchall()]
    return {"events": events}
