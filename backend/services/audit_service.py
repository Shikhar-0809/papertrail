"""Audit service: read-only queries for audit_log with center joins."""

import json
import logging

import aiosqlite

from backend.database import get_db

logger = logging.getLogger(__name__)

_EVENT_COLUMNS = """
    al.id, al.event_type, al.exam_id, al.center_id, al.ip_address,
    al.severity, al.rule_id, al.details, al.human_readable, al.timestamp,
    ec.center_code, ec.name AS center_name
"""

_BASE_FROM = """
    FROM audit_log al
    LEFT JOIN exam_centers ec ON al.center_id = ec.id
"""


def _build_filters(
    exam_id: str | None,
    center_id: str | None,
    severity: str | None,
) -> tuple[str, list[str | int]]:
    """Return (WHERE clause suffix, params) for audit_log filters."""
    where_parts: list[str] = []
    params: list[str | int] = []
    if exam_id:
        where_parts.append("al.exam_id = ?")
        params.append(exam_id)
    if center_id:
        where_parts.append("al.center_id = ?")
        params.append(center_id)
    if severity:
        where_parts.append("al.severity = ?")
        params.append(severity)
    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
    return where_sql, params


def _parse_details(raw: str | None) -> dict | None:
    """Parse audit_log.details JSON text into a dict."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid audit_log details JSON: %r", raw[:80])
        return None
    return parsed if isinstance(parsed, dict) else None


def _action_taken(details: dict | None, rule_id: str | None) -> str | None:
    """Derive action_taken from details or rule_id for alert responses."""
    if details:
        action = details.get("action") or details.get("action_taken")
        if isinstance(action, str):
            return action
    if rule_id == "R001":
        return "key_blocked"
    if rule_id == "R003":
        return "flagged"
    return None


def _make_alert_id(timestamp: str, row_id: int) -> str:
    """Build alert_id as ALR-YYYYMMDD-#### per API_CONTRACTS.md."""
    date_part = timestamp[:10].replace("-", "")
    return f"ALR-{date_part}-{row_id:04d}"


def _row_to_event(row: aiosqlite.Row) -> dict:
    """Map a joined audit_log row to the GET /api/audit/log event shape."""
    return {
        "id": row["id"],
        "event_type": row["event_type"],
        "exam_id": row["exam_id"],
        "center_id": row["center_id"],
        "center_code": row["center_code"],
        "center_name": row["center_name"],
        "ip_address": row["ip_address"],
        "severity": row["severity"],
        "rule_id": row["rule_id"],
        "details": _parse_details(row["details"]),
        "human_readable": row["human_readable"],
        "timestamp": row["timestamp"],
    }


def _row_to_alert(row: aiosqlite.Row) -> dict:
    """Map a joined audit_log row to the GET /api/audit/alerts alert shape."""
    details = _parse_details(row["details"])
    return {
        "alert_id": _make_alert_id(row["timestamp"], row["id"]),
        "rule_id": row["rule_id"],
        "severity": row["severity"],
        "center_code": row["center_code"],
        "center_name": row["center_name"],
        "triggered_at": row["timestamp"],
        "human_readable": row["human_readable"],
        "action_taken": _action_taken(details, row["rule_id"]),
        "center_id": row["center_id"],
    }


async def get_audit_log(
    exam_id: str | None,
    center_id: str | None,
    severity: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """Return paginated audit events with center_code and center_name."""
    where_sql, params = _build_filters(exam_id, center_id, severity)
    async with get_db() as db:
        count_cur = await db.execute(
            "SELECT COUNT(*) FROM audit_log al" + where_sql,
            params,
        )
        total = int((await count_cur.fetchone())[0])
        cur = await db.execute(
            "SELECT " + _EVENT_COLUMNS + _BASE_FROM + where_sql
            + " ORDER BY al.timestamp DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        events = [_row_to_event(r) for r in await cur.fetchall()]
    logger.debug("get_audit_log: returned %d/%d events", len(events), total)
    return events, total


async def get_alerts() -> list[dict]:
    """Return active alerts (severity HIGH or CRITICAL) in API contract shape."""
    async with get_db() as db:
        cur = await db.execute(
            "SELECT " + _EVENT_COLUMNS + _BASE_FROM
            + " WHERE al.severity IN ('HIGH', 'CRITICAL')"
            + " ORDER BY al.timestamp DESC",
        )
        alerts = [_row_to_alert(r) for r in await cur.fetchall()]
    logger.debug("get_alerts: returned %d alerts", len(alerts))
    return alerts
