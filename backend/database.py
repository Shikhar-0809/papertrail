"""
Async database layer: connection context manager and schema initialisation.
No business logic lives here — only connection setup and table definitions.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import aiosqlite

from backend.config import DB_PATH

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yield an aiosqlite connection with WAL mode and foreign keys enabled."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db() -> None:
    """Create all tables if they do not exist. Called once at startup."""
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS exam_centers (
                id          TEXT PRIMARY KEY,
                center_code TEXT UNIQUE NOT NULL,
                name        TEXT NOT NULL,
                city        TEXT NOT NULL,
                state       TEXT NOT NULL,
                latitude    REAL,
                longitude   REAL,
                created_at  TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id             TEXT PRIMARY KEY,
                name           TEXT NOT NULL,
                subject        TEXT NOT NULL,
                scheduled_at   TEXT NOT NULL,
                key_release_at TEXT NOT NULL,
                status         TEXT NOT NULL DEFAULT 'draft',
                created_at     TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS exam_center_assignments (
                exam_id   TEXT NOT NULL REFERENCES exams(id),
                center_id TEXT NOT NULL REFERENCES exam_centers(id),
                PRIMARY KEY (exam_id, center_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS vault (
                id                TEXT PRIMARY KEY,
                exam_id           TEXT NOT NULL REFERENCES exams(id),
                center_id         TEXT NOT NULL REFERENCES exam_centers(id),
                encrypted_pdf_path TEXT,
                aes_key_b64       TEXT NOT NULL,
                release_at        TEXT NOT NULL,
                is_released       INTEGER NOT NULL DEFAULT 0,
                released_at       TEXT,
                created_at        TEXT NOT NULL,
                UNIQUE(exam_id, center_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS watermarks (
                id           TEXT PRIMARY KEY,
                exam_id      TEXT NOT NULL REFERENCES exams(id),
                center_id    TEXT NOT NULL REFERENCES exam_centers(id),
                bit_sequence TEXT NOT NULL,
                created_at   TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS forensic_reports (
                id              TEXT PRIMARY KEY,
                status          TEXT NOT NULL DEFAULT 'processing',
                confidence      REAL,
                center_id       TEXT REFERENCES exam_centers(id),
                exam_id         TEXT REFERENCES exams(id),
                grids_detected  INTEGER,
                grids_valid     INTEGER,
                raw_bits        TEXT,
                analysis_ms     INTEGER,
                error_message   TEXT,
                created_at      TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type     TEXT NOT NULL,
                exam_id        TEXT,
                center_id      TEXT,
                ip_address     TEXT,
                severity       TEXT NOT NULL,
                rule_id        TEXT,
                details        TEXT,
                human_readable TEXT NOT NULL,
                timestamp      TEXT NOT NULL
            )
        """)
        await db.commit()
    logger.info("Database schema initialised at %s", DB_PATH)
