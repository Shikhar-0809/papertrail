# Coding Standards

Cursor must follow every rule in this document when generating any file in this project. These standards exist to ensure the codebase reads as if one senior engineer wrote it, is maintainable, and has no category of hidden bugs that appear only at runtime.

---

## 1. Language and Runtime

- Python 3.11+ for all backend code
- Node 20+ for frontend
- No Python 2 syntax or compatibility shims

---

## 2. Type Hints — Mandatory Everywhere

Every function must have complete type hints. No exceptions.

```python
# FORBIDDEN
def get_exam(exam_id):
    pass

def process(data, flag=False):
    return data

# REQUIRED
async def get_exam(exam_id: str) -> Exam | None:
    pass

def process(data: bytes, flag: bool = False) -> ProcessResult:
    return ProcessResult(data=data)
```

Return type `None` must be explicit when the function returns nothing:
```python
async def log_event(event: AuditEvent) -> None:
    await db.execute(...)
```

---

## 3. Pydantic Models for All API Boundaries

Every request body and every response body must be a Pydantic model. No raw dicts crossing API boundaries.

```python
# FORBIDDEN in routes
@router.post("/exams")
async def create_exam(data: dict):  # raw dict
    name = data["name"]

# REQUIRED
class CreateExamRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    subject: str = Field(..., min_length=1, max_length=100)
    scheduled_at: datetime
    center_ids: list[str] = Field(..., min_items=1)

class ExamResponse(BaseModel):
    id: str
    name: str
    status: str
    scheduled_at: datetime
    total_centers: int

@router.post("/exams", response_model=ExamResponse)
async def create_exam(request: CreateExamRequest) -> ExamResponse:
    ...
```

---

## 4. Async Everywhere in Backend

All route functions and service functions must be `async`. All database calls must use `await`.

```python
# FORBIDDEN — synchronous in an async context
def get_center(center_id: str) -> Center:
    conn = sqlite3.connect("examshield.db")
    ...

# REQUIRED
async def get_center(center_id: str) -> Center | None:
    async with get_db() as db:
        ...
```

Exception: utility functions in `watermark/` and `crypto/` that are pure computation (no I/O) may be synchronous. They should be called with `asyncio.run_in_executor` if they are slow.

---

## 5. Error Handling — Layered Pattern

Each layer handles errors appropriate to its concern:

```
watermark/ and crypto/  → raise domain-specific exceptions (WatermarkError, EncryptionError)
services/               → catch domain exceptions, raise ServiceError with context
routes/                 → catch ServiceError, raise HTTPException with appropriate status code
main.py global handler  → catch everything else, return 500 with generic message
```

```python
# watermark/decoder.py
class WatermarkError(Exception):
    pass

class ExtractionFailed(WatermarkError):
    pass

def extract_center_id(image: np.ndarray) -> ForensicResult:
    if image is None or image.size == 0:
        raise ExtractionFailed("Empty or null image provided")

# services/forensics_service.py
from backend.watermark.decoder import ExtractionFailed, WatermarkError

async def analyze(file_path: Path, report_id: str) -> None:
    try:
        result = decoder.extract_center_id(image)
    except ExtractionFailed as e:
        logger.warning(f"Extraction failed for report {report_id}: {e}")
        await db_update_report(report_id, status="failed", error=str(e))
    except WatermarkError as e:
        logger.error(f"Watermark error for report {report_id}: {e}", exc_info=True)
        await db_update_report(report_id, status="failed", error="Processing error")

# routes/forensics_routes.py
@router.post("/forensics/analyze")
async def analyze_image(file: UploadFile) -> AnalyzeResponse:
    try:
        report_id = await forensics_service.start_analysis(file)
        return AnalyzeResponse(report_id=report_id, status="processing")
    except FileTooLargeError:
        raise HTTPException(413, "File too large")
    except UnsupportedMimeError:
        raise HTTPException(415, "Unsupported file type")
```

**Rule**: Never let an exception propagate from a service into a route unhandled. Never let an exception from `watermark/` or `crypto/` reach the HTTP layer directly.

---

## 6. Logging — Structured, Never print()

Use Python's `logging` module. Never `print()` in production code (tests are exempt).

```python
# At top of every module
import logging
logger = logging.getLogger(__name__)

# Log format (configured in main.py):
# 2026-06-14 08:23:41 INFO  backend.services.vault_service — key_released exam=NEET-2026 center=NEET-HAZ-221 ip=103.21.88.14

# Usage
logger.info(f"Key released: exam={exam_id} center={center_id} ip={ip}")
logger.warning(f"Premature key request: center={center_id} minutes_early={minutes}")
logger.error(f"Extraction failed: report={report_id}", exc_info=True)

# FORBIDDEN — leaks sensitive data
logger.info(f"Key value: {key_b64}")
logger.debug(f"Full vault entry: {vault_entry}")
```

---

## 7. File Length Limit

No Python file should exceed 250 lines (excluding comments and blank lines). If a file approaches this limit, split it.

```
# If paper_service.py is getting long:
paper_service.py         → exam CRUD operations
paper_generator.py       → PDF generation and watermarking orchestration
```

---

## 8. Function Length Limit

No function should exceed 40 lines. If it does, extract sub-functions.

---

## 9. Constants — Named, Never Magic Numbers

```python
# FORBIDDEN
if len(content) > 15728640:  # what is this?
    raise HTTPException(413, ...)

if confidence > 0.75:  # where did 0.75 come from?

# REQUIRED — in config.py or at top of the relevant module
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15MB
MIN_CONFIDENCE_THRESHOLD = 0.75      # minimum for "identified" status
GRID_ROWS = 6
GRID_COLS = 6
GRID_SPACING_PX = 20
MARKER_SIZE_PX = 6
MARKER_COLOR = (180, 180, 180)
```

---

## 10. Database Access Pattern

Always use the async context manager pattern. Never hold a connection open across await points unnecessarily.

```python
# In database.py — define this once
from contextlib import asynccontextmanager
import aiosqlite

@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

# In services — use it like this
async def get_exam(exam_id: str) -> Exam | None:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM exams WHERE id = ?",
            (exam_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Exam(**dict(row))
```

---

## 11. Route Functions — Thin

Route functions must do exactly three things: parse input, call one service function, return response. No business logic.

```python
# REQUIRED pattern — thin route
@router.post("/forensics/analyze", response_model=AnalyzeResponse)
async def analyze_image(file: UploadFile = File(...)) -> AnalyzeResponse:
    report_id = await forensics_service.start_analysis(file)
    return AnalyzeResponse(report_id=report_id, status="processing")

# FORBIDDEN — fat route with business logic
@router.post("/forensics/analyze")
async def analyze_image(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > 15728640:  # business logic in route
        raise HTTPException(413, ...)
    mime = magic.from_buffer(content, mime=True)  # validation in route
    if mime not in {"image/jpeg", "image/png"}:
        raise HTTPException(415, ...)
    # ... 30 more lines
```

---

## 12. Frontend Standards

### Component Structure

```jsx
// Every component: props typed with JSDoc or PropTypes, single responsibility
function ForensicResult({ report, onReset }) {
  // 1. State declarations
  // 2. Effect hooks
  // 3. Event handlers
  // 4. Render (no logic here, only JSX)
  return (...)
}
```

### API Calls — Only in api.js

```javascript
// FORBIDDEN — fetch() inside a component
function Dashboard() {
  useEffect(() => {
    fetch('http://localhost:8000/api/dashboard/stats')  // hardcoded URL in component
      .then(...)
  }, [])
}

// REQUIRED — all API calls through api.js
// api.js
const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000'
export const getDashboardStats = () => fetch(`${BASE_URL}/api/dashboard/stats`).then(r => r.json())

// Component
import { getDashboardStats } from '../api'
function Dashboard() {
  useEffect(() => {
    getDashboardStats().then(setStats)
  }, [])
}
```

### No Inline Styles

Use Tailwind classes only. No `style={{}}` props except for dynamic values that cannot be expressed in Tailwind (e.g., dynamically computed widths).

---

## 13. Test Structure

Every service function needs at least one test. Test files mirror the source structure.

```
backend/services/vault_service.py → tests/test_vault_service.py
backend/watermark/encoder.py      → tests/test_watermark_roundtrip.py
backend/watermark/decoder.py      → tests/test_watermark_roundtrip.py (same file)
```

Test naming:
```python
def test_key_released_after_release_time():      # describes the scenario
def test_key_blocked_before_release_time():
def test_rule_r001_fires_on_early_request():
def test_encoder_decoder_roundtrip_center_221():
def test_crc_detects_single_bit_flip():
```

---

## 14. Environment Variables

All configuration from environment. `config.py` reads env vars and fails loudly if required ones are missing.

```python
# config.py
import os
from pathlib import Path

def _require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Required environment variable {key} is not set. "
                          f"See README.md for setup instructions.")
    return value

# Required — app won't start without these
MASTER_KEY_HEX: str = _require_env("EXAMSHIELD_MASTER_KEY")

# Optional with defaults — app starts but logs a warning
DB_PATH: Path = Path(os.environ.get("EXAMSHIELD_DB_PATH", "examshield.db"))
UPLOADS_DIR: Path = Path(os.environ.get("EXAMSHIELD_UPLOADS_DIR", "/tmp/examshield_uploads"))
ALLOWED_ORIGINS: list[str] = os.environ.get("EXAMSHIELD_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
```

A `.env.example` file must exist in the repo with all variable names but no real values:
```
EXAMSHIELD_MASTER_KEY=generate-with-python-secrets-token-hex-32
EXAMSHIELD_DB_PATH=examshield.db
EXAMSHIELD_UPLOADS_DIR=/tmp/examshield_uploads
EXAMSHIELD_ALLOWED_ORIGINS=http://localhost:3000
```

`.env` itself must be in `.gitignore`. Never commit real values.
