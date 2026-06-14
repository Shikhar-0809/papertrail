"""Shared audit-log write helper used by vault_service and anomaly_service."""

import json
import logging
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger(__name__)


async def write_audit(
    event_type: str,
    severity: str,
    human_readable: str,
    exam_id: str,
    center_id: str,
    ip_address: str,
    db: aiosqlite.Connection,
    rule_id: str | None = None,
    details: dict | None = None,
) -> None:
    """Insert one row into audit_log and commit. All SQL parameterized (S-003)."""
    await db.execute(
        """
        INSERT INTO audit_log
            (event_type, exam_id, center_id, ip_address,
             severity, rule_id, details, human_readable, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_type,
            exam_id,
            center_id,
            ip_address,
            severity,
            rule_id,
            json.dumps(details) if details else None,
            human_readable,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await db.commit()
    logger.debug("audit_log: event=%s exam=%s center=%s", event_type, exam_id, center_id)
