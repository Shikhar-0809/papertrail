# Security Audit Checklists

Run the audit for your current milestone after completing it. Document every finding. Fix before moving to the next milestone. Commit audit fixes separately from feature commits with prefix `security(MX-audit):`.

---

## M1 Audit — Watermark Engine

Run after: encoder.py, decoder.py, crc.py, simulator.py are complete and tests pass.

### Input Validation

```bash
# Run edge case tests
python -m pytest tests/test_watermark_edge_cases.py -v
```

Manual checks — verify each returns gracefully (no unhandled exception, no crash):

| Input | Expected Behavior | Pass/Fail | Notes |
|-------|------------------|-----------|-------|
| `embed_markers(image, center_id=0, ...)` | Returns image with all-zero grid | | |
| `embed_markers(image, center_id=65535, ...)` | Returns image with all-one center_id bits | | |
| `embed_markers(image, center_id=-1, ...)` | Raises ValueError immediately | | |
| `embed_markers(image, center_id=70000, ...)` | Raises ValueError (exceeds 16-bit) | | |
| `embed_markers(image, page_num=16, ...)` | Raises ValueError (exceeds 4-bit) | | |
| `extract_center_id(np.zeros((10,10), uint8))` | Returns status="failed", no crash | | |
| `extract_center_id(np.ones((3508,2480), uint8)*255)` | Returns status="inconclusive", no crash | | |
| `extract_center_id(random_noise_image)` | Returns status="inconclusive" or "failed" | | |

### CRC Integrity

```python
# Run in Python shell — verify CRC detects corruption
from backend.watermark.crc import compute_crc8, verify_crc8
from backend.watermark.encoder import embed_markers
from backend.watermark.decoder import extract_center_id

# Encode
result = extract_center_id(embed_markers(base_image, 221, 1, 1))
assert result.center_id == 221, "Roundtrip failed"

# Verify single bit flip detection
# (test_watermark_roundtrip.py should cover this automatically)
```

### Accuracy Test

```bash
python -m pytest tests/test_watermark_accuracy.py -v -s
# Must show ≥17/20 successful extractions
# Record result in WATERMARK_SPEC.md "Tuned Parameters" section
```

**M1 Audit Result**: PASS
**Date**: 2026-06-14
**Findings**:
  - BUGS-010: Simulator rotation border fill caused 0% extraction accuracy.
    Root cause: white borderValue in _step_rotation destroyed dark canvas
    frame, giving page boundary detector 8+ corners instead of 4.
    Fixed in ad9e7db (one line).
  - BUGS-004: Corrected stated rotation limit from ±8° to ±0.22° in BUGS.md.
  - decoder.py exceeded 250-line limit (was 348 lines).
    Refactored into decoder.py + decoder_pipeline.py + decoder_result.py.
  - All-zeros CRC false positive closed with _ALL_ZEROS_SENTINEL guard.
**Actions taken**: All findings resolved before M2. See commits for details.

---

## M2 Audit — Backend API

Run after: all FastAPI routes, services, vault, anomaly engine are complete.

### Automated Checks

```bash
# 1. No hardcoded secrets
grep -rn "password\|secret\|api_key\|master_key" backend/ --include="*.py" \
  | grep -v "environ\|SECURITY\|BUGS\|#\|test"
# Expected: 0 results

# 2. No SQL string formatting (injection risk)
grep -rn 'f"SELECT\|f"INSERT\|f"UPDATE\|f"DELETE\|f"DROP' backend/ --include="*.py"
# Expected: 0 results

# 3. No bare except
grep -rn "except:" backend/ --include="*.py"
# Expected: 0 results

# 4. No print statements in production code
grep -rn "^    print(\|^print(" backend/ --include="*.py" \
  | grep -v "test_\|seed.py"
# Expected: 0 results

# 5. No stack traces in HTTP responses
grep -rn "traceback\|format_exc" backend/routes/ --include="*.py"
# Expected: 0 results

# 6. Bandit static analysis
bandit -r backend/ -ll
# Fix all MEDIUM and HIGH severity findings before proceeding

# 7. Dependency vulnerabilities
safety check -r requirements.txt
# Fix any HIGH severity CVEs
```

### File Upload Attack Tests

Start the server: `uvicorn backend.main:app --reload`

```bash
# Test 1: Oversized file (should return 413)
dd if=/dev/zero bs=1M count=20 > /tmp/bigfile.bin
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/forensics/analyze \
  -F "file=@/tmp/bigfile.bin;type=image/jpeg"
# Expected: 413

# Test 2: Wrong MIME type — Python script disguised as JPEG (should return 415)
echo "import os; os.system('whoami')" > /tmp/evil.py
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/forensics/analyze \
  -F "file=@/tmp/evil.py;type=image/jpeg"
# Expected: 415

# Test 3: Path traversal in filename (server should use UUID filename, ignore this)
curl -s -X POST http://localhost:8000/api/forensics/analyze \
  -F "file=@/tmp/photo.jpg" \
  -F "filename=../../backend/config.py"
# Expected: 200 (processed normally) — server MUST ignore client filename
# Verify: ls /tmp/examshield_uploads/ — should show UUID filename, not config.py

# Test 4: Empty file (should return 400 or 415)
touch /tmp/empty.jpg
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/forensics/analyze \
  -F "file=@/tmp/empty.jpg"
# Expected: 400 or 415, not 500

# Test 5: Valid JPEG (should return 200 with report_id)
curl -s -X POST http://localhost:8000/api/forensics/analyze \
  -F "file=@demo/test_photos/leaked_center_221.jpg"
# Expected: 200, {"report_id": "...", "status": "processing"}
```

**Record results**:
| Test | Expected | Actual | Pass/Fail |
|------|----------|--------|-----------|
| Oversized file | 413 | | |
| Wrong MIME | 415 | | |
| Path traversal | 200 (UUID filename used) | | |
| Empty file | 400 or 415 | | |
| Valid JPEG | 200 | | |

### Time-Lock Attack Tests

```bash
# Test 1: Early key request (before release_at)
# Setup: create exam with release_at = 2 hours from now
# Then immediately request key

curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/api/vault/release/EXAM-ID/NEET-HAZ-221
# Expected: 403

# Verify alert was logged
curl -s http://localhost:8000/api/audit/alerts | python3 -m json.tool | grep "R001"
# Expected: alert with rule_id=R001, severity=CRITICAL

# Test 2: Key request at correct time
# Manually set release_at to 1 minute ago in DB for testing
sqlite3 examshield.db "UPDATE vault SET release_at = datetime('now', '-1 minute') WHERE center_id = 'NEET-HAZ-221'"

curl -s http://localhost:8000/api/vault/release/EXAM-ID/NEET-HAZ-221
# Expected: 200 with key in response

# Test 3: Replay — request key again after release
curl -s http://localhost:8000/api/vault/release/EXAM-ID/NEET-HAZ-221
# Expected: 200 again (key can be re-requested — it's already released)
# But audit log should show second request
```

### IDOR Test

```bash
# Can center A request center B's key?
# In production this would use auth tokens, in MVP we test the logic directly

# Request HAZ-221's key using PAT-442's exam context (wrong center)
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/api/vault/release/EXAM-ID/NEET-HAZ-221
# The endpoint looks up by (exam_id, center_id) — verify it only returns
# data for the exact center_id requested, not any center

# Verify: does requesting a nonexistent center return 404 (not 500)?
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/api/vault/release/EXAM-ID/FAKE-CENTER-999
# Expected: 404
```

### Error Message Information Leakage

```bash
# Trigger DB error — request nonexistent exam
curl -s http://localhost:8000/api/exams/definitely-not-a-real-uuid
# Expected: {"error": "Not found"} or {"error": "Exam not found"}
# FORBIDDEN: any SQLite error message, any Python traceback

# Trigger validation error
curl -s http://localhost:8000/api/vault/release/../../etc/passwd/CENTER
# Expected: 400 with generic message
# FORBIDDEN: 500, any path information in response

# Trigger OpenCV error via bad image
echo "not an image" > /tmp/notanimage.jpg
curl -s -X POST http://localhost:8000/api/forensics/analyze \
  -F "file=@/tmp/notanimage.jpg;type=image/jpeg"
# Expected: {"error": "Could not process image", "code": "FORENSICS_FAILED"}
# FORBIDDEN: OpenCV error string, Python traceback
```

### Rate Limiting Test

```bash
# Hammer vault endpoint — should trigger R003 after 3 requests
for i in {1..15}; do
  curl -s -o /dev/null -w "$i: %{http_code}\n" \
    http://localhost:8000/api/vault/release/EXAM-ID/NEET-HAZ-221
done
# Expected: first few 200/403, then 429 after rate limit
# Check: curl http://localhost:8000/api/audit/alerts | grep R003
```

**M2 Audit Result**: PASS
**Date**: 2026-06-14
**Findings**:
  1. JSONResponse positional argument bug — all error returns in vault_routes.py
     and forensics_routes.py used JSONResponse(status_code, content) positional
     form, passing status code as content and dict as status_code. Caused 500
     on all error paths. Fixed: 6 calls converted to keyword arguments.
  2. Automated checks (secrets/SQL/bare-except/print/stack-traces): all clean.
     4 secret-pattern hits confirmed false positives (config var names +
     stdlib secrets module import).
  3. Path traversal attempt (/../../etc/passwd): blocked by Starlette URL
     normalisation before reaching route. Returns 404, not our custom 400.
     Acceptable for MVP — URL normalisation is a valid first defence.
     S-009 regex validation fires correctly for well-formed but invalid IDs.
**Actions taken**: JSONResponse keyword argument fix applied before closing audit.
                   All other findings require no code change.

---

## M3 Audit — Frontend

Run after: all React pages are complete and wired to the API.

### Browser Storage Check

```bash
# Should return zero results
grep -rn "localStorage\|sessionStorage\|document\.cookie" frontend/src/ --include="*.jsx" --include="*.js"
# Expected: 0 results — no sensitive data in browser storage
```

### XSS Check

```bash
# Verify no dangerouslySetInnerHTML usage
grep -rn "dangerouslySetInnerHTML" frontend/src/ --include="*.jsx"
# Expected: 0 results

# Verify no direct innerHTML assignment
grep -rn "innerHTML" frontend/src/ --include="*.jsx" --include="*.js"
# Expected: 0 results
```

### API URL Hardcoding

```bash
# API base URL should only appear in api.js
grep -rn "localhost:8000\|127.0.0.1:8000" frontend/src/ --include="*.jsx" --include="*.js"
# Expected: only in src/api.js or config file, nowhere else
```

### Manual Browser Tests

Open browser DevTools → Network tab, then:

| Action | Check | Pass/Fail |
|--------|-------|-----------|
| Load dashboard | No AES key values in any network response | |
| Upload forensic photo | Response contains report_id, NOT raw bits or key | |
| View audit log | Center codes visible, no keys visible | |
| Open DevTools → Application → Storage | localStorage and sessionStorage are empty | |
| Open DevTools → Console | No sensitive values logged to console | |

**M3 Audit Result**: PASS
**Date**: 2026-06-14
**Findings**:
  1. "Invalid Date" in AuditTrail, Dashboard, ForensicsLab — ISO timestamp
     strings not parsed correctly. Fixed with formatDate() helper in all
     three components.
  2. All automated checks clean: no localStorage, no dangerouslySetInnerHTML,
     no hardcoded URLs outside api.js, no fetch() in components.
**Actions taken**: formatDate helper added to AuditTrail.jsx, Dashboard.jsx,
                   ForensicsLab.jsx before closing M3.

---

## M4 Audit — Integration Attack Simulation

Run after: full system is integrated and demo data is seeded. This is your final check before recording the demo video.

### Scenario 1: Insider Early Access

```
Setup: NEET-HAZ-221 exam, release_at = 2 hours from now
Action: Request key from NEET-HAZ-221
Expected:
  ✓ 403 response
  ✓ Rule R001 alert in audit log with correct center and timing info
  ✓ Alert appears on dashboard within 5 seconds (auto-refresh)
  ✓ Center marker on India map turns amber/red
Pass/Fail: ___
Notes:
```

### Scenario 2: Wrong Center Key Request

```
Setup: Keys for all 10 centers stored
Action: Request NEET-HAZ-221's key — verify only that exact center's data returned
Action: Request key for NEET-FAKE-999 (nonexistent)
Expected:
  ✓ Only returns key for the exact (exam_id, center_id) requested
  ✓ 404 for nonexistent center
  ✓ Both attempts logged in audit
Pass/Fail: ___
Notes:
```

### Scenario 3: Forensics Rapid Upload

```
Action: Upload 15 images in rapid succession to /api/forensics/analyze
Expected:
  ✓ First 10 succeed (or rate limit after configured threshold)
  ✓ Excess requests return 429
  ✓ All attempts appear in audit log
Pass/Fail: ___
Notes:
```

### Scenario 4: PDF Tampering Detection

```python
# Generate test in Python
from backend.crypto.aes import encrypt, decrypt
from backend.crypto.keygen import generate_key

key = generate_key()
pdf_bytes = b"fake exam content" * 1000
ciphertext = encrypt(pdf_bytes, key)

# Tamper with 5 bytes in the middle
tampered = bytearray(ciphertext)
tampered[len(tampered)//2 : len(tampered)//2 + 5] = b'\x00' * 5
tampered = bytes(tampered)

# Attempt decryption
try:
    result = decrypt(tampered, key)
    print("FAIL — tampered ciphertext decrypted successfully")
except Exception as e:
    print(f"PASS — tampered ciphertext rejected: {type(e).__name__}")
```

```
Expected: Exception raised (InvalidTag or similar)
Pass/Fail: ___
Notes:
```

### Scenario 5: Partial Watermark Survival

```python
# In Python:
from backend.watermark.encoder import embed_markers
from backend.watermark.decoder import extract_center_id
from backend.watermark.simulator import simulate_leak_photo
import cv2, numpy as np

# Generate watermarked page
base = np.ones((3508, 2480), dtype=np.uint8) * 255
watermarked = embed_markers(base, center_id=221, exam_id=1, page_num=1)

# Paint over bottom-right corner (destroy one grid)
watermarked[3300:, 2200:] = 255

# Simulate degradation
degraded = simulate_leak_photo(watermarked, rotation_deg=3.0, jpeg_quality=70)

# Extract
result = extract_center_id(degraded)
print(f"Status: {result.status}, Center: {result.center_id}, Confidence: {result.confidence}")
```

```
Expected: status="identified", center_id=221, confidence ≈ 0.75 (3/4 grids)
Pass/Fail: ___
Notes:
```

### Final Pre-Demo Checklist

```
[ ] Demo seed data loaded (10 centers, NEET 2026 exam, full audit history)
[ ] test_photos/leaked_center_221.jpg exists and extracts correctly (verified)
[ ] Dashboard shows correct stats
[ ] Alert banner fires when R001 is triggered manually
[ ] Forensics Lab uploads complete without errors
[ ] Audit trail shows all simulated events
[ ] Server runs without errors for 10+ minutes
[ ] No sensitive values in browser console
[ ] GitHub repo is public, clean, no secrets
[ ] requirements.txt matches actual installed packages
[ ] Fresh clone + pip install + python seed.py + uvicorn works
```

**M4 Audit Result**: PASS / FAIL  
**Date**: ___________  
**Findings**:  
**Actions taken**:  
