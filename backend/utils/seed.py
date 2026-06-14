"""Database seed: 10 centers, 1 exam, watermarked+encrypted papers, audit history.

Owns ONLY database population. Watermark + crypto generation is delegated to
``exam_service.generate_papers()`` — seed.py must never call encoder/ or crypto/
directly (ARCHITECTURE.md). Idempotent: running twice creates no duplicate data.
No hardcoded secrets — the AES master key is read from the environment by
``backend.config`` at import time (S-001).
"""

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone

from backend.database import get_db, init_db
from backend.services import exam_service
from backend.services.audit_helpers import write_audit

logger = logging.getLogger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_EXAM_ID = "01000000-0000-4000-8000-000000000001"
_EXAM_NAME = "NEET-UG 2026"
_EXAM_SUBJECT = "Physics, Chemistry, Biology"

# (id, center_code, name, city, state, latitude, longitude)
# IDs are zero-padded "001".."010" EXCEPT center #7, whose id is "221" — the
# WATERMARK_SPEC.md canonical test vector. forensics_service resolves a decoded
# watermark integer to a center via `exam_centers.id == str(decoded_int)`, so
# this id makes the demo leak photo (center 221) identify end-to-end.
_CENTERS: list[tuple[str, str, str, str, str, float, float]] = [
    ("001", "NEET-DEL-001", "Kendriya Vidyalaya RK Puram", "New Delhi", "Delhi", 28.5639, 77.1750),
    ("002", "NEET-MUM-002", "St. Xavier's College", "Mumbai", "Maharashtra", 18.9440, 72.8312),
    ("003", "NEET-KOL-003", "Presidency University", "Kolkata", "West Bengal", 22.5757, 88.3629),
    ("004", "NEET-CHN-004", "DAV Senior Secondary School", "Chennai", "Tamil Nadu", 13.0827, 80.2707),
    ("005", "NEET-BLR-005", "National Public School", "Bengaluru", "Karnataka", 12.9716, 77.5946),
    ("006", "NEET-HYD-006", "Narayana Junior College", "Hyderabad", "Telangana", 17.3850, 78.4867),
    ("221", "NEET-HAZ-221", "Oasis School Hazaribagh", "Hazaribagh", "Jharkhand", 23.9925, 85.3637),
    ("008", "NEET-JAI-008", "Maharaja College", "Jaipur", "Rajasthan", 26.9124, 75.7873),
    ("009", "NEET-PAT-009", "Patna Collegiate School", "Patna", "Bihar", 25.5941, 85.1376),
    ("010", "NEET-LKO-010", "La Martiniere College", "Lucknow", "Uttar Pradesh", 26.8467, 80.9462),
]

# (event_type, severity, center_id, ip_address, rule_id, human_readable, details)
_AUDIT_EVENTS: list[tuple[str, str, str, str, str | None, str, dict | None]] = [
    ("anomaly_r001", "CRITICAL", "002", "103.21.88.14", "R001",
     "Center NEET-MUM-002 attempted key access 47 minutes early from 103.21.88.14",
     {"minutes_early": 47, "action": "key_blocked"}),
    ("anomaly_r001", "CRITICAL", "005", "49.36.120.7", "R001",
     "Center NEET-BLR-005 attempted key access 31 minutes early from 49.36.120.7",
     {"minutes_early": 31, "action": "key_blocked"}),
    ("anomaly_r001", "CRITICAL", "221", "103.156.19.200", "R001",
     "Center NEET-HAZ-221 attempted key access 52 minutes early from 103.156.19.200",
     {"minutes_early": 52, "action": "key_blocked"}),
    ("key_released", "INFO", "001", "103.21.88.30", None,
     "Key released: exam=NEET-UG 2026 center=NEET-DEL-001 ip=103.21.88.30", None),
    ("forensic_match", "CRITICAL", "221", "", None,
     "Leaked paper identified: center=NEET-HAZ-221 confidence=75.0%",
     {"confidence": 0.75, "grids_valid": 3}),
]


async def _seed_centers(db) -> None:  # type: ignore[no-untyped-def]
    """Insert all 10 centers. INSERT OR IGNORE keeps this idempotent."""
    now = datetime.now(timezone.utc).isoformat()
    for cid, code, name, city, state, lat, lon in _CENTERS:
        await db.execute(
            "INSERT OR IGNORE INTO exam_centers "
            "(id, center_code, name, city, state, latitude, longitude, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, code, name, city, state, lat, lon, now),
        )
    logger.info("Seeded %d exam centers", len(_CENTERS))


async def _seed_exam(db) -> None:  # type: ignore[no-untyped-def]
    """Insert the draft exam + center assignments if not already present."""
    cur = await db.execute("SELECT 1 FROM exams WHERE id = ?", (_EXAM_ID,))
    if await cur.fetchone() is not None:
        logger.info("Exam %s already present — skipping insert", _EXAM_NAME)
        return
    tomorrow = (datetime.now(_IST) + timedelta(days=1)).date()
    scheduled = datetime.combine(tomorrow, time(9, 0), _IST).isoformat()
    release = datetime.combine(tomorrow, time(8, 30), _IST).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO exams "
        "(id, name, subject, scheduled_at, key_release_at, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'draft', ?)",
        (_EXAM_ID, _EXAM_NAME, _EXAM_SUBJECT, scheduled, release, now),
    )
    for cid, *_rest in _CENTERS:
        await db.execute(
            "INSERT OR IGNORE INTO exam_center_assignments (exam_id, center_id) "
            "VALUES (?, ?)",
            (_EXAM_ID, cid),
        )
    logger.info("Created exam %s scheduled=%s release=%s", _EXAM_NAME, scheduled, release)


async def _generate_papers_if_needed() -> None:
    """Delegate watermark + encryption to the service layer (idempotent)."""
    async with get_db() as db:
        cur = await db.execute("SELECT status FROM exams WHERE id = ?", (_EXAM_ID,))
        row = await cur.fetchone()
    if row is None:
        return
    if row["status"] != "draft":
        logger.info("Papers already generated (status=%s) — skipping", row["status"])
        return
    result = await exam_service.generate_papers(_EXAM_ID)
    logger.info("Generated papers: %s", result)


async def _seed_audit_history(db) -> None:  # type: ignore[no-untyped-def]
    """Write a realistic audit trail. Skips if R001 events already exist."""
    cur = await db.execute(
        "SELECT COUNT(*) FROM audit_log WHERE exam_id = ? AND rule_id = 'R001'",
        (_EXAM_ID,),
    )
    if (await cur.fetchone())[0] > 0:
        logger.info("Audit history already seeded — skipping")
        return
    for event_type, severity, center_id, ip, rule_id, text, details in _AUDIT_EVENTS:
        await write_audit(
            event_type=event_type, severity=severity, human_readable=text,
            exam_id=_EXAM_ID, center_id=center_id, ip_address=ip, db=db,
            rule_id=rule_id, details=details,
        )
    logger.info("Seeded %d audit events", len(_AUDIT_EVENTS))


async def main() -> None:
    """Populate the database for demo/dev. Safe to run repeatedly."""
    await init_db()
    async with get_db() as db:
        await _seed_centers(db)
        await _seed_exam(db)
        await db.commit()
    await _generate_papers_if_needed()
    async with get_db() as db:
        await _seed_audit_history(db)
    logger.info("Seed complete: %d centers, exam '%s', papers + audit history.",
                len(_CENTERS), _EXAM_NAME)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    asyncio.run(main())
