"""Forensics service: validate uploads, run watermark extraction, persist results.

S-004 file validation applied in start_analysis. No exceptions escape _run_analysis.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiosqlite
import cv2
import magic
from fastapi import UploadFile

from backend.config import ALLOWED_MIMES, MAX_UPLOAD_BYTES, UPLOADS_DIR
from backend.database import get_db
from backend.services.audit_helpers import write_audit
from backend.watermark.decoder import extract_center_id

logger = logging.getLogger(__name__)


class FileTooLargeError(Exception): pass
class UnsupportedMimeError(Exception): pass


async def start_analysis(file: UploadFile) -> str:
    """Validate, save, create DB record, launch background task. Returns report_id."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise FileTooLargeError(f"Upload exceeds {MAX_UPLOAD_BYTES} bytes")
    mime: str = magic.from_buffer(content, mime=True)
    if mime not in ALLOWED_MIMES:
        raise UnsupportedMimeError(f"Unsupported MIME type: {mime}")
    file_path = UPLOADS_DIR / f"{uuid4()}.jpg"
    file_path.write_bytes(content)

    report_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO forensic_reports (id, status, created_at) VALUES (?, ?, ?)",
            (report_id, "processing", now),
        )
        await db.commit()

    asyncio.create_task(_run_analysis(file_path, report_id))
    logger.info("Analysis queued: report=%s", report_id)
    return report_id


async def get_report(report_id: str) -> dict | None:
    """Fetch one report. Returns None if not found."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT fr.id, fr.status, fr.confidence, fr.grids_detected, fr.grids_valid,
                   fr.raw_bits, fr.analysis_ms, fr.error_message, fr.created_at,
                   fr.center_id, fr.exam_id,
                   ec.center_code, ec.name AS center_name,
                   ec.city, ec.state, ec.latitude, ec.longitude,
                   e.name AS exam_name
            FROM forensic_reports fr
            LEFT JOIN exam_centers ec ON ec.id = fr.center_id
            LEFT JOIN exams e ON e.id = fr.exam_id
            WHERE fr.id = ?
            """,
            (report_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        return None

    base: dict = {"report_id": row["id"], "status": row["status"], "created_at": row["created_at"]}
    if row["status"] == "processing":
        return base

    center = {"id": row["center_id"], "center_code": row["center_code"],
              "name": row["center_name"], "city": row["city"], "state": row["state"],
              "latitude": row["latitude"], "longitude": row["longitude"],
              } if row["center_id"] else None
    exam = {"id": row["exam_id"], "name": row["exam_name"]} if row["exam_id"] else None
    base.update({"confidence": row["confidence"], "analysis_ms": row["analysis_ms"],
                 "grids_detected": row["grids_detected"], "grids_valid": row["grids_valid"],
                 "raw_bits": row["raw_bits"], "center": center, "exam": exam})
    if row["status"] == "inconclusive":
        base["message"] = (
            "Insufficient grid data. Image may be too degraded or not a watermarked paper."
        )
    return base


async def list_reports() -> list[dict]:
    """Return all reports newest-first, matching GET /api/forensics/reports."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT fr.id, fr.status, fr.confidence, fr.created_at,
                   ec.center_code, ec.name AS center_name
            FROM forensic_reports fr
            LEFT JOIN exam_centers ec ON ec.id = fr.center_id
            ORDER BY fr.created_at DESC
            """,
        )
        rows = await cursor.fetchall()
    return [
        {
            "report_id": r["id"],
            "status": r["status"],
            "confidence": r["confidence"],
            "center_code": r["center_code"],
            "center_name": r["center_name"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


async def _mark_failed(report_id: str, message: str) -> None:
    try:
        async with get_db() as db:
            await db.execute(
                "UPDATE forensic_reports SET status='failed', error_message=? WHERE id=?",
                (message, report_id),
            )
            await db.commit()
    except aiosqlite.Error as exc:
        logger.error("Could not mark report=%s failed: %s", report_id, exc)


async def _run_analysis(file_path: Path, report_id: str) -> None:
    """Decode watermark and persist result. Never lets exceptions escape."""
    try:
        image = cv2.imread(str(file_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            await _mark_failed(report_id, "Could not read image")
            return

        result = extract_center_id(image)
        status = result.status
        db_center_id: str | None = None
        db_exam_id: str | None = None
        center_code: str | None = None

        async with get_db() as db:
            if result.center_id is not None:
                cur = await db.execute(
                    "SELECT id, center_code FROM exam_centers WHERE CAST(id AS TEXT) = ? LIMIT 1",
                    (str(result.center_id),),
                )
                cc_row = await cur.fetchone()
                if cc_row:
                    db_center_id = cc_row["id"]
                    center_code = cc_row["center_code"]

                wm_cur = await db.execute(
                    "SELECT exam_id FROM watermarks WHERE center_id = ? LIMIT 1",
                    (db_center_id or str(result.center_id),),
                )
                wm_row = await wm_cur.fetchone()
                db_exam_id = wm_row["exam_id"] if wm_row else None

            await db.execute(
                "UPDATE forensic_reports "
                "SET status=?, confidence=?, grids_detected=?, grids_valid=?, "
                "    raw_bits=?, analysis_ms=?, center_id=?, exam_id=? WHERE id=?",
                (status, result.confidence, result.grids_detected, result.grids_valid,
                 result.raw_bits, result.analysis_ms, db_center_id, db_exam_id, report_id),
            )
            await db.commit()

            if db_center_id is not None:
                await write_audit(
                    event_type="forensic_match",
                    severity="CRITICAL",
                    human_readable=(
                        f"Leaked paper identified: center={center_code} "
                        f"confidence={result.confidence:.1%}"
                    ),
                    exam_id=db_exam_id or "",
                    center_id=db_center_id,
                    ip_address="",
                    db=db,
                )

        logger.info("Analysis complete: report=%s status=%s", report_id, status)

    except cv2.error as exc:
        logger.error("OpenCV error: report=%s %s", report_id, exc)
        await _mark_failed(report_id, "Image processing error")
    except Exception as exc:
        logger.error("Unexpected error: report=%s %s", report_id, exc, exc_info=True)
        await _mark_failed(report_id, "Internal analysis error")
