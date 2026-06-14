"""Exam CRUD and paper generation service."""

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import aiosqlite
import cv2
import numpy as np

from backend.config import UPLOADS_DIR
from backend.crypto.aes import encrypt as aes_encrypt
from backend.crypto.keygen import generate_key, key_to_b64
from backend.database import get_db
from backend.utils.pdf_generator import generate_page
from backend.watermark.crc import compute_crc8
from backend.watermark.encoder import embed_markers

logger = logging.getLogger(__name__)


class AlreadyGeneratedError(Exception):
    pass


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _center_int(uuid_str: str) -> int:
    """Deterministic 16-bit int from center UUID."""
    return int(uuid_str.replace("-", "")[:4], 16) & 0xFFFF


def _exam_int(uuid_str: str) -> int:
    """Deterministic 8-bit int from exam UUID."""
    return int(uuid_str.replace("-", "")[:2], 16) & 0xFF


def _image_to_bytes(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError("cv2.imencode failed")
    return buf.tobytes()


def _bit_sequence(center_int: int, exam_int: int, page: int = 1) -> str:
    data = [(center_int >> (15 - i)) & 1 for i in range(16)]
    data += [(exam_int >> (7 - i)) & 1 for i in range(8)]
    data += [(page >> (3 - i)) & 1 for i in range(4)]
    return "".join(str(b) for b in data + compute_crc8(data))


async def _store_paper(
    exam_id: str, exam_i: int,
    center_id: str, center_i: int,
    release_at: str, db: aiosqlite.Connection,
) -> None:
    """Generate key once, encrypt, store. Never logs the key (S-002)."""
    key = generate_key()
    watermarked = embed_markers(generate_page(), center_i, exam_i, 1)
    ciphertext = aes_encrypt(_image_to_bytes(watermarked), key)
    enc_path = UPLOADS_DIR / f"{exam_id}_{center_id}.enc"
    enc_path.write_bytes(ciphertext)
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT OR REPLACE INTO vault "
        "(id, exam_id, center_id, encrypted_pdf_path, aes_key_b64, release_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid4()), exam_id, center_id, str(enc_path), key_to_b64(key), release_at, now),
    )
    await db.execute(
        "INSERT INTO watermarks (id, exam_id, center_id, bit_sequence, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid4()), exam_id, center_id, _bit_sequence(center_i, exam_i), now),
    )
    logger.info("Paper stored: exam=%s center=%s", exam_id, center_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def list_exams() -> dict:
    async with get_db() as db:
        cur = await db.execute(
            "SELECT e.id, e.name, e.subject, e.scheduled_at, e.key_release_at, "
            "e.status, e.created_at, COUNT(eca.center_id) AS total_centers "
            "FROM exams e "
            "LEFT JOIN exam_center_assignments eca ON eca.exam_id = e.id "
            "GROUP BY e.id ORDER BY e.created_at DESC"
        )
        rows = await cur.fetchall()
    exams = [dict(r) for r in rows]
    return {"exams": exams, "total": len(exams)}


async def get_exam(exam_id: str) -> dict | None:
    async with get_db() as db:
        ecur = await db.execute("SELECT * FROM exams WHERE id=?", (exam_id,))
        exam = await ecur.fetchone()
        if not exam:
            return None
        ccur = await db.execute(
            "SELECT ec.id, ec.center_code, ec.name, ec.city, ec.state, "
            "v.encrypted_pdf_path, v.is_released "
            "FROM exam_center_assignments eca "
            "JOIN exam_centers ec ON ec.id = eca.center_id "
            "LEFT JOIN vault v ON v.exam_id=eca.exam_id AND v.center_id=ec.id "
            "WHERE eca.exam_id=?", (exam_id,),
        )
        centers = []
        for c in await ccur.fetchall():
            acur = await db.execute(
                "SELECT COUNT(*), SUM(severity='CRITICAL') FROM audit_log "
                "WHERE center_id=? AND severity IN ('HIGH','CRITICAL')", (c["id"],),
            )
            arow = await acur.fetchone()
            alert_count = arow[0] or 0
            status = "compromised" if (arow[1] or 0) > 0 else "flagged" if alert_count > 0 else "normal"
            centers.append({
                "center_id": c["id"], "center_code": c["center_code"],
                "center_name": c["name"], "city": c["city"], "state": c["state"],
                "paper_generated": c["encrypted_pdf_path"] is not None,
                "key_released": bool(c["is_released"]), "alert_count": alert_count,
                "status": status,
            })
    return {
        "id": exam["id"], "name": exam["name"], "subject": exam["subject"],
        "scheduled_at": exam["scheduled_at"], "key_release_at": exam["key_release_at"],
        "status": exam["status"], "centers": centers,
    }


async def create_exam(
    name: str, subject: str,
    scheduled_at: datetime, center_ids: list[str],
) -> dict:
    exam_id = str(uuid4())
    key_release_at = scheduled_at - timedelta(minutes=30)
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO exams (id, name, subject, scheduled_at, key_release_at, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'draft', ?)",
            (exam_id, name, subject, scheduled_at.isoformat(), key_release_at.isoformat(), now),
        )
        for cid in center_ids:
            await db.execute(
                "INSERT INTO exam_center_assignments (exam_id, center_id) VALUES (?, ?)",
                (exam_id, cid),
            )
        await db.commit()
    logger.info("Exam created: id=%s name=%s centers=%d", exam_id, name, len(center_ids))
    return {
        "id": exam_id, "name": name, "subject": subject,
        "scheduled_at": scheduled_at.isoformat(), "key_release_at": key_release_at.isoformat(),
        "total_centers": len(center_ids), "status": "draft", "created_at": now,
    }


async def generate_papers(exam_id: str) -> dict:
    async with get_db() as db:
        ecur = await db.execute(
            "SELECT status, key_release_at FROM exams WHERE id=?", (exam_id,),
        )
        exam_row = await ecur.fetchone()
        if not exam_row or exam_row["status"] != "draft":
            raise AlreadyGeneratedError(f"Exam {exam_id} is not in draft status")
        release_at = exam_row["key_release_at"]
        exam_i = _exam_int(exam_id)
        ccur = await db.execute(
            "SELECT center_id FROM exam_center_assignments WHERE exam_id=?", (exam_id,),
        )
        center_rows = await ccur.fetchall()
        for row in center_rows:
            cid = row["center_id"]
            await _store_paper(exam_id, exam_i, cid, _center_int(cid), release_at, db)
        await db.execute("UPDATE exams SET status='distributed' WHERE id=?", (exam_id,))
        await db.commit()
    n = len(center_rows)
    logger.info("Papers generated: exam=%s count=%d", exam_id, n)
    return {"exam_id": exam_id, "generated": n, "failed": 0,
            "message": f"Papers generated and encrypted for {n} centers"}
