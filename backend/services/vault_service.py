"""Vault service: enforces time-lock and releases AES keys.

Follows ARCHITECTURE.md "Key Release (Time-Lock)" data flow exactly.
Never logs key values (S-002). All SQL parameterized (S-003).
"""

import logging
from datetime import datetime, timezone

import aiosqlite

from backend.database import get_db
from backend.services import anomaly_service
from backend.services.anomaly_service import AnomalyContext
from backend.services.audit_helpers import write_audit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class KeyNotYetAvailable(Exception):
    def __init__(self, release_at: datetime, minutes_remaining: int) -> None:
        self.release_at = release_at
        self.minutes_remaining = minutes_remaining
        super().__init__(f"Key not available until {release_at.isoformat()}")


class VaultEntryNotFound(Exception):
    pass


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _fetch_vault_entry(
    exam_id: str,
    center_id: str,
    db: aiosqlite.Connection,
) -> aiosqlite.Row | None:
    """SELECT vault entry joined with center_code."""
    cursor = await db.execute(
        """
        SELECT v.id, v.aes_key_b64, v.release_at, v.is_released, v.released_at,
               ec.center_code
        FROM vault v
        JOIN exam_centers ec ON ec.id = v.center_id
        WHERE v.exam_id = ? AND v.center_id = ?
        """,
        (exam_id, center_id),
    )
    return await cursor.fetchone()


async def _count_recent_requests(
    center_id: str,
    db: aiosqlite.Connection,
) -> int:
    """Count key_request events for this center in the last 60 seconds."""
    cursor = await db.execute(
        """
        SELECT COUNT(*) FROM audit_log
        WHERE center_id = ?
          AND event_type = 'key_request'
          AND timestamp > datetime('now', '-60 seconds')
        """,
        (center_id,),
    )
    row = await cursor.fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def release_key(
    exam_id: str,
    center_id: str,
    ip_address: str,
) -> dict:
    """Main key-release flow. Raises VaultEntryNotFound or KeyNotYetAvailable."""
    async with get_db() as db:
        row = await _fetch_vault_entry(exam_id, center_id, db)
        if row is None:
            raise VaultEntryNotFound(f"No vault entry for exam={exam_id} center={center_id}")

        center_code: str = row["center_code"]
        release_at_raw: str = row["release_at"]
        release_at = datetime.fromisoformat(release_at_raw).replace(tzinfo=timezone.utc)

        await write_audit(
            event_type="key_request",
            severity="INFO",
            human_readable=f"Key requested: exam={exam_id} center={center_code} ip={ip_address}",
            exam_id=exam_id,
            center_id=center_id,
            ip_address=ip_address,
            db=db,
        )

        now = datetime.now(timezone.utc)
        context = AnomalyContext(
            exam_id=exam_id,
            center_id=center_id,
            center_code=center_code,
            ip_address=ip_address,
            requested_at=now,
            release_at=release_at,
            request_count_last_minute=await _count_recent_requests(center_id, db),
        )

        r001_alert = await anomaly_service.evaluate("R001", context, db)
        if r001_alert is not None:
            delta = release_at - now
            minutes_remaining = max(1, int(delta.total_seconds() / 60))
            raise KeyNotYetAvailable(release_at, minutes_remaining)

        await anomaly_service.evaluate_all(context, db)

        released_at_iso = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE vault SET is_released=1, released_at=? WHERE id=?",
            (released_at_iso, row["id"]),
        )
        await db.commit()

        await write_audit(
            event_type="key_released",
            severity="INFO",
            human_readable=f"Key released: exam={exam_id} center={center_code} ip={ip_address}",
            exam_id=exam_id,
            center_id=center_id,
            ip_address=ip_address,
            db=db,
        )
        # S-002: log event identifiers only — never the key value
        logger.info("Key released: exam=%s center=%s ip=%s", exam_id, center_id, ip_address)

        return {
            "key": row["aes_key_b64"],
            "algorithm": "AES-256-GCM",
            "released_at": released_at_iso,
        }


async def get_vault_status(exam_id: str) -> dict:
    """Return key-release status for all centers in an exam."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT v.center_id, ec.center_code, v.release_at,
                   v.is_released, v.released_at
            FROM vault v
            JOIN exam_centers ec ON ec.id = v.center_id
            WHERE v.exam_id = ?
            ORDER BY ec.center_code
            """,
            (exam_id,),
        )
        rows = await cursor.fetchall()

    key_release_at = rows[0]["release_at"] if rows else None
    return {
        "exam_id": exam_id,
        "key_release_at": key_release_at,
        "centers": [
            {
                "center_id": r["center_id"],
                "center_code": r["center_code"],
                "is_released": bool(r["is_released"]),
                "released_at": r["released_at"],
            }
            for r in rows
        ],
    }
