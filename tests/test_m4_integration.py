"""M4 integration tests — the 5 attack scenarios from SECURITY_AUDIT.md.

Drives the live FastAPI app in-process via httpx.AsyncClient + ASGITransport
(no separate uvicorn). Each test sets up and tears down its own data and never
depends on seed.py having run.
"""

import io
import os

# Set a throwaway master key BEFORE importing the app, so importing config never
# fails during collection (tests are exempt from the production env requirement).
os.environ.setdefault("EXAMSHIELD_MASTER_KEY", "00" * 32)

from datetime import datetime, timedelta, timezone  # noqa: E402
from uuid import uuid4  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from cryptography.exceptions import InvalidTag  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from backend.crypto.aes import decrypt, encrypt  # noqa: E402
from backend.crypto.keygen import generate_key  # noqa: E402
from backend.database import get_db, init_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.watermark.decoder import extract_center_id  # noqa: E402
from backend.watermark.encoder import embed_markers  # noqa: E402
from backend.watermark.simulator import simulate_leak_photo  # noqa: E402

pytestmark = pytest.mark.asyncio

_TRANSPORT = ASGITransport(app=app)
_SCENARIO5_SEED = 7  # deterministic degradation so confidence is reproducible


def _client() -> AsyncClient:
    return AsyncClient(transport=_TRANSPORT, base_url="http://test")


async def _insert_vault(exam_id: str, center_id: str, release_at: str, code: str) -> None:
    """Insert a center + exam + vault row so the release endpoint has data."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO exam_centers "
            "(id, center_code, name, city, state, created_at) "
            "VALUES (?, ?, 'Test Center', 'Testville', 'Teststate', ?)",
            (center_id, code, now),
        )
        await db.execute(
            "INSERT OR IGNORE INTO exams "
            "(id, name, subject, scheduled_at, key_release_at, status, created_at) "
            "VALUES (?, 'Test Exam', 'Testing', ?, ?, 'distributed', ?)",
            (exam_id, release_at, release_at, now),
        )
        await db.execute(
            "INSERT OR REPLACE INTO vault "
            "(id, exam_id, center_id, encrypted_pdf_path, aes_key_b64, release_at, created_at) "
            "VALUES (?, ?, ?, '/tmp/x.enc', 'ZHVtbXlrZXk=', ?, ?)",
            (str(uuid4()), exam_id, center_id, release_at, now),
        )
        await db.commit()


async def _cleanup(exam_id: str, *center_ids: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM audit_log WHERE exam_id = ?", (exam_id,))
        await db.execute("DELETE FROM vault WHERE exam_id = ?", (exam_id,))
        await db.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
        for cid in center_ids:
            await db.execute("DELETE FROM exam_centers WHERE id = ?", (cid,))
        await db.commit()


def _tiny_jpeg() -> bytes:
    ok, buf = cv2.imencode(".jpg", np.full((16, 16), 200, dtype=np.uint8))
    return buf.tobytes()


# --- Scenario 1: Insider early access --------------------------------------

async def test_key_blocked_before_release_time() -> None:
    await init_db()
    exam_id, center_id = str(uuid4()), "INSIDER001"
    release_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    await _insert_vault(exam_id, center_id, release_at, "NEET-INS-001")
    try:
        async with _client() as c:
            resp = await c.get(f"/api/vault/release/{exam_id}/{center_id}")
        assert resp.status_code == 403
        assert resp.json()["code"] == "KEY_NOT_YET_AVAILABLE"
    finally:
        await _cleanup(exam_id, center_id)


async def test_rule_r001_alert_fires_on_early_request() -> None:
    await init_db()
    exam_id, center_id = str(uuid4()), "INSIDER002"
    release_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    await _insert_vault(exam_id, center_id, release_at, "NEET-INS-002")
    try:
        async with _client() as c:
            await c.get(f"/api/vault/release/{exam_id}/{center_id}")
            alerts = (await c.get("/api/audit/alerts")).json()["alerts"]
        async with get_db() as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE center_id=? AND rule_id='R001' AND severity='CRITICAL'",
                (center_id,),
            )
            r001_count = (await cur.fetchone())[0]
        assert r001_count >= 1
        assert any(a.get("center_id") == center_id and a.get("rule_id") == "R001" for a in alerts)
    finally:
        await _cleanup(exam_id, center_id)


# --- Scenario 2: IDOR / wrong center ---------------------------------------

async def test_idor_nonexistent_center_returns_404() -> None:
    await init_db()
    exam_id, real_center = str(uuid4()), "VALIDCTR01"
    release_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    await _insert_vault(exam_id, real_center, release_at, "NEET-VAL-001")
    try:
        async with _client() as c:
            missing = await c.get(f"/api/vault/release/{exam_id}/NOSUCHCENTER")
            mismatch = await c.get(f"/api/vault/release/{uuid4()}/{real_center}")
        assert missing.status_code == 404
        assert mismatch.status_code == 404
        assert "key" not in mismatch.json()
    finally:
        await _cleanup(exam_id, real_center)


# --- Scenario 3: Forensics rapid upload (rate limit) -----------------------

async def test_rate_limit_fires_after_threshold() -> None:
    await init_db()
    jpeg = _tiny_jpeg()
    statuses: list[int] = []
    async with _client() as c:
        for _ in range(15):
            resp = await c.post(
                "/api/forensics/analyze",
                files={"file": ("leak.jpg", io.BytesIO(jpeg), "image/jpeg")},
            )
            statuses.append(resp.status_code)
    assert 429 in statuses
    assert all(s == 200 for s in statuses if s != 429)


# --- Scenario 4: PDF tampering detection (unit) ----------------------------

async def test_aes_gcm_rejects_tampered_ciphertext() -> None:
    key = generate_key()
    ciphertext = encrypt(b"confidential exam content " * 40, key)
    tampered = bytearray(ciphertext)
    mid = len(tampered) // 2
    for i in range(mid, mid + 5):
        tampered[i] ^= 0xFF
    with pytest.raises(InvalidTag):
        decrypt(bytes(tampered), key)


# --- Scenario 5: Partial watermark survival --------------------------------

async def test_partial_watermark_identifies_center() -> None:
    page = np.full((3508, 2480), 255, dtype=np.uint8)
    wm = embed_markers(page, center_id=221, exam_id=1, page_num=1)
    wm[3300:, 2200:] = 255  # destroy the bottom-right grid
    np.random.seed(_SCENARIO5_SEED)
    degraded = simulate_leak_photo(wm, rotation_deg=3.0, jpeg_quality=70)
    result = extract_center_id(degraded)
    assert result.status == "identified"
    assert result.center_id == 221
    assert result.confidence >= 0.75
