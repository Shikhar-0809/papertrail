# ExamShield — Architecture

## System Overview

ExamShield is a single FastAPI application with a React frontend. It is NOT a microservices architecture. One `uvicorn` process runs everything. One SQLite database stores everything. This is a deliberate MVP choice — the architecture is stateless enough that scaling to PostgreSQL + multiple workers requires only config changes, not restructuring.

```
┌─────────────────────────────────────────────────────────────┐
│                     React Frontend                          │
│         (Dashboard / ExamManager / ForensicsLab /           │
│                      AuditTrail)                            │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP REST (JSON)
                         │ multipart/form-data (file upload)
┌────────────────────────▼────────────────────────────────────┐
│                  FastAPI Application                        │
│                                                             │
│  ┌─────────────┐ ┌─────────────┐ ┌────────────────────┐    │
│  │exam_routes  │ │vault_routes │ │forensics_routes    │    │
│  │dashboard_   │ │audit_routes │ │                    │    │
│  │routes       │ │             │ │                    │    │
│  └──────┬──────┘ └──────┬──────┘ └─────────┬──────────┘    │
│         │               │                  │               │
│  ┌──────▼──────┐ ┌──────▼──────┐ ┌─────────▼──────────┐    │
│  │paper_service│ │vault_service│ │forensics_service   │    │
│  │             │ │             │ │                    │    │
│  │             │ │anomaly_     │ │                    │    │
│  │             │ │service      │ │                    │    │
│  └──────┬──────┘ └──────┬──────┘ └─────────┬──────────┘    │
│         │               │                  │               │
│  ┌──────▼───────────────▼──────────────────▼──────────┐    │
│  │              watermark/  +  crypto/                │    │
│  │         (encoder, decoder, aes, keygen)            │    │
│  └──────────────────────┬─────────────────────────────┘    │
│                         │                                   │
│  ┌──────────────────────▼─────────────────────────────┐    │
│  │                   SQLite DB                        │    │
│  │     (aiosqlite — async, single file)               │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Ownership

Each module owns specific responsibilities. Cursor must NOT bleed logic across these boundaries.

### `watermark/encoder.py`
**Owns**: Converting (center_id, exam_id, page_num) into a visual dot grid embedded in an image.
**Does NOT own**: PDF creation, file I/O, database access, HTTP concerns.
**Exports**: `embed_markers(image: np.ndarray, center_id: int, exam_id: int, page_num: int) -> np.ndarray`

### `watermark/decoder.py`
**Owns**: Extracting center_id from a degraded image of a printed exam paper.
**Does NOT own**: Database lookups, HTTP concerns, file I/O.
**Exports**: `extract_center_id(image: np.ndarray) -> ForensicResult`

### `watermark/crc.py`
**Owns**: CRC-8 checksum computation only.
**Exports**: `compute_crc8(bits: list[int]) -> list[int]`, `verify_crc8(bits: list[int]) -> bool`

### `watermark/simulator.py`
**Owns**: Simulating print→photo→WhatsApp degradation pipeline for testing.
**Does NOT own**: Any production code path. Used only in tests and demo generation.
**Exports**: `simulate_leak_photo(image: np.ndarray) -> np.ndarray`

### `crypto/aes.py`
**Owns**: AES-256-GCM encryption and decryption of bytes.
**Does NOT own**: Key generation, key storage, file I/O.
**Exports**: `encrypt(plaintext: bytes, key: bytes) -> bytes`, `decrypt(ciphertext: bytes, key: bytes) -> bytes`

### `crypto/keygen.py`
**Owns**: Generating cryptographically random AES keys. Base64 encoding/decoding helpers.
**Exports**: `generate_key() -> bytes`, `key_to_b64(key: bytes) -> str`, `b64_to_key(b64: str) -> bytes`

### `services/paper_service.py`
**Owns**: Creating exams, assigning centers, generating watermarked+encrypted PDFs, distributing.
**Calls**: `watermark/encoder.py`, `crypto/aes.py`, `crypto/keygen.py`, `utils/pdf_generator.py`, database.
**Does NOT own**: Route handling, HTTP responses, vault logic, forensics logic.

### `services/vault_service.py`
**Owns**: Storing keys, enforcing time-lock, releasing keys, triggering anomaly evaluation.
**Calls**: `services/anomaly_service.py`, database.
**Does NOT own**: AES operations (only stores/retrieves base64 keys), route handling.

### `services/anomaly_service.py`
**Owns**: Evaluating all anomaly rules, writing alerts to audit_log.
**Does NOT own**: Blocking requests (it only logs — the vault_service decides to block based on anomaly results).
**Exports**: `evaluate(rule_id: str, context: AnomalyContext) -> Alert | None`, `evaluate_all(context: AnomalyContext) -> list[Alert]`

### `services/forensics_service.py`
**Owns**: Orchestrating file upload → image decode → watermark extraction → DB result write.
**Calls**: `watermark/decoder.py`, database.
**Does NOT own**: HTTP file handling (that's the route), watermark math (that's decoder).

### `routes/*.py`
**Owns**: HTTP request parsing, calling exactly one service function, returning HTTP response.
**Does NOT own**: Business logic, database access, watermark math.
**Rule**: No route function should exceed 20 lines. If it does, the logic belongs in a service.

### `utils/pdf_generator.py`
**Owns**: Generating a realistic A4 exam paper as a PIL Image object.
**Does NOT own**: Watermarking (paper_service calls encoder after getting the image).

### `utils/seed.py`
**Owns**: Populating the database with 10 exam centers and 1 sample exam for demo/dev.
**Does NOT own**: Anything else.

---

## Data Flow: Paper Generation

```
POST /api/exams/{exam_id}/generate
    → exam_routes.py
    → paper_service.generate_papers(exam_id)
        → db: fetch exam + all assigned centers
        → for each center:
            → pdf_generator.generate_page() → PIL Image
            → encoder.embed_markers(image, center_id, exam_id, page=1) → watermarked Image
            → convert watermarked Image to bytes (PDF)
            → keygen.generate_key() → key bytes
            → aes.encrypt(pdf_bytes, key) → ciphertext
            → db: store encrypted PDF path + key in vault
            → db: store watermark bit_sequence in watermarks table
        → db: update exam status = 'distributed'
    → return: {"generated": N, "exam_id": exam_id}
```

## Data Flow: Forensic Analysis

```
POST /api/forensics/analyze (multipart: file)
    → forensics_routes.py
        → validate file: mime type, size limit
        → save to uploads/ with UUID filename
    → forensics_service.analyze(file_path, report_id)
        → db: create forensic_report record (status=processing)
        → image = cv2.imread(file_path, GRAYSCALE)
        → result = decoder.extract_center_id(image)
        → db: update forensic_report with result
        → if result.center_id found:
            → db: write audit_log entry (FORENSIC_MATCH, CRITICAL severity)
    → return: {"report_id": report_id, "status": "processing"}

GET /api/forensics/report/{report_id}
    → forensics_routes.py
    → db: fetch forensic_report
    → return full result including center details
```

## Data Flow: Key Release (Time-Lock)

```
GET /api/vault/release/{exam_id}/{center_id}
    → vault_routes.py
    → vault_service.release_key(exam_id, center_id, ip)
        → db: fetch vault entry
        → db: write audit_log (key_request, INFO)
        → anomaly_service.evaluate("R001", context) — premature access check
        → if now < release_at:
            → db: write audit_log (key_denied, CRITICAL)
            → raise 403
        → anomaly_service.evaluate_all(context) — all other rules
        → db: mark vault entry as released
        → db: write audit_log (key_released, INFO)
        → return: {"key": base64_key, "algorithm": "AES-256-GCM"}
```

---

## What Cursor Must Never Do

- Access the database from a route function directly
- Put business logic inside a route function
- Import from `routes/` inside `services/`
- Import from `services/` inside `watermark/` or `crypto/`
- Use `print()` anywhere (use `logging`)
- Catch bare `except:` without re-raising or specific exception type
- Return Python exceptions or stack traces in HTTP responses
- Store the AES key in any variable named generically like `data` or `result` where it might be logged
