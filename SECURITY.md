# Security — Threat Model and Generation Rules

## Threat Model

### Who Is the Attacker

**Primary**: An insider at an exam center (principal, invigilator, or vendor staff) who has physical access to printed exam papers before the exam starts. They have a smartphone, access to WhatsApp/Telegram, and are connected to an organized exam mafia network.

**Secondary**: A network attacker who can observe or manipulate HTTP traffic between exam centers and the ExamShield server.

**Out of scope for MVP**: Nation-state attackers, side-channel attacks on the server, physical attacks on the server hardware.

### What the Attacker Can Do

- Access the ExamShield web UI from the exam center's IP address
- Make HTTP requests to any API endpoint
- Try to request decryption keys before the scheduled exam time
- Try to request another center's decryption key
- Upload arbitrary files to the forensics endpoint
- Try to access the server's file system via path traversal
- Try to extract information from error messages

### What the Attacker Cannot Do (Our Guarantees)

- Decrypt the exam PDF without the AES key (AES-256-GCM guarantee)
- Modify the encrypted PDF without detection (GCM authentication tag guarantee)
- Obtain the key before release_at time (time-lock guarantee)
- Identify which exam center a leaked paper came from without ExamShield (watermark guarantee)

---

## Mandatory Rules for Code Generation

Cursor must follow every rule in this section. No exceptions. If a rule conflicts with convenience, the rule wins.

### Rule S-001: No Hardcoded Secrets

```python
# FORBIDDEN — Cursor must never generate this
SECRET_KEY = "mysecretkey123"
MASTER_KEY = b"hardcodedkey32b"
DB_PASSWORD = "admin"

# REQUIRED — always from environment
import os
SECRET_KEY = os.environ["EXAMSHIELD_SECRET_KEY"]
MASTER_KEY = bytes.fromhex(os.environ["EXAMSHIELD_MASTER_KEY"])
```

If an environment variable is missing, the application must fail to start with a clear error, not fall back to a default.

### Rule S-002: AES Keys Are Never Logged

```python
# FORBIDDEN
logger.info(f"Releasing key: {key_b64}")
logger.debug(f"Vault entry: {vault_entry}")  # vault_entry contains the key

# REQUIRED — log the event, never the key value
logger.info(f"Key released for exam={exam_id} center={center_id} ip={ip}")
```

The string "aes_key" or "key_b64" must never appear as a value in any log statement.

### Rule S-003: Parameterized Queries Only

```python
# FORBIDDEN — SQL injection risk
query = f"SELECT * FROM centers WHERE city = '{city}'"
query = "SELECT * FROM exams WHERE id = " + exam_id

# REQUIRED — parameterized always
query = "SELECT * FROM centers WHERE city = ?"
await db.execute(query, (city,))
```

### Rule S-004: File Upload Validation

Every file upload endpoint must validate in this exact order before processing:

```python
# 1. Size check (before reading content)
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15MB
content = await file.read(MAX_UPLOAD_BYTES + 1)
if len(content) > MAX_UPLOAD_BYTES:
    raise HTTPException(413, "File too large. Maximum 15MB.")

# 2. MIME type check from file bytes (not extension, not Content-Type header)
import magic
mime = magic.from_buffer(content, mime=True)
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}
if mime not in ALLOWED_MIMES:
    raise HTTPException(415, "Unsupported file type. Upload JPEG, PNG, or WebP.")

# 3. Save with UUID filename, NEVER use client-provided filename
import uuid
safe_filename = f"{uuid.uuid4()}.jpg"
upload_path = UPLOADS_DIR / safe_filename  # UPLOADS_DIR is outside web root
```

### Rule S-005: No Stack Traces in HTTP Responses

```python
# FORBIDDEN
raise HTTPException(500, detail=str(e))  # exposes internal info
return {"error": traceback.format_exc()}

# REQUIRED — generic message, full trace only in server logs
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL_ERROR"}
    )
```

### Rule S-006: CORS — Explicit Origins Only

```python
# FORBIDDEN
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# REQUIRED
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)
```

### Rule S-007: No Direct Database Access from Routes

Routes call services. Services access the database. Never:
```python
# FORBIDDEN in any route file
async def get_exam(exam_id: str, db = Depends(get_db)):
    result = await db.execute("SELECT * FROM exams WHERE id = ?", (exam_id,))
    return result  # business logic in route
```

### Rule S-008: Specific Exception Handling

```python
# FORBIDDEN
try:
    result = decoder.extract_center_id(image)
except:
    return None

# REQUIRED — catch specific, log all
try:
    result = decoder.extract_center_id(image)
except cv2.error as e:
    logger.error(f"OpenCV error during extraction: {e}")
    raise ForensicsExtractionError(f"Image processing failed: {type(e).__name__}")
except ValueError as e:
    logger.error(f"Invalid image data: {e}")
    raise ForensicsExtractionError("Invalid image format")
```

### Rule S-009: Input Validation on All Route Parameters

```python
# Every route parameter that maps to a DB lookup must validate format
# before hitting the database

async def release_key(exam_id: str, center_id: str):
    # Validate format before DB query
    if not re.match(r'^[A-Z0-9_-]{3,50}$', center_id):
        raise HTTPException(400, "Invalid center_id format")
    if not re.match(r'^[a-f0-9-]{36}$', exam_id):  # UUID format
        raise HTTPException(400, "Invalid exam_id format")
    # Now safe to query DB
```

### Rule S-010: Uploads Directory Configuration

```python
# config.py must define this
UPLOADS_DIR = Path(os.environ.get("UPLOADS_DIR", "/tmp/examshield_uploads"))
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# UPLOADS_DIR must NOT be inside the FastAPI static files directory
# UPLOADS_DIR must NOT be accessible via any HTTP route
```

---

## Security Audit Integration

After each milestone, run the corresponding audit from `SECURITY_AUDIT.md`. Document findings. Fix before proceeding.

The following commands must produce zero results before submission:

```bash
# No hardcoded secrets
grep -rn "password\|secret\|api_key\|master_key" backend/ --include="*.py" | grep -v "environ\|SECURITY\|#"

# No SQL string formatting
grep -rn 'f"SELECT\|f"INSERT\|f"UPDATE\|f"DELETE' backend/ --include="*.py"

# No stack traces in responses
grep -rn "traceback\|format_exc\|str(e)" backend/routes/ --include="*.py"

# No bare except
grep -rn "except:" backend/ --include="*.py"

# No print statements
grep -rn "^    print(\|^print(" backend/ --include="*.py"

# Security static analysis
bandit -r backend/ -ll --exit-zero

# Dependency vulnerability check
safety check -r requirements.txt
```

---

## Known Security Limitations (Honest)

These are MVP tradeoffs. They are documented in BUGS.md. Do not fix them by introducing worse solutions.

**L-001**: Time-lock is server-enforced, not cryptographic. A compromised server process could release keys early. Production fix: HSM.

**L-002**: AES keys stored as base64 in SQLite. They are not encrypted at rest in the MVP. Production fix: encrypt vault entries with a master key stored in HSM or KMS.

**L-003**: No authentication on API endpoints. MVP relies on center_code in request. Production fix: mTLS or signed JWT tokens per center with biometric verification.

**L-004**: Single SQLite file has no access controls beyond OS file permissions. Production fix: PostgreSQL with role-based access.

Do NOT attempt to "fix" L-001 through L-004 with partial solutions that create false security. A fake cryptographic time-lock is worse than an honest server-enforced one because it misleads users about the security guarantee.
