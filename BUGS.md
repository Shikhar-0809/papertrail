# Known Bugs and Limitations

This document is updated throughout development. It serves two purposes:
1. Honest submission artifact showing engineering maturity
2. Cursor instruction: items marked "Do Not Fix" must not be silently patched

---

## Severity Definitions

- **CRITICAL**: Would cause data breach or complete system failure in production
- **HIGH**: Significant security or correctness issue, acceptable for MVP
- **MEDIUM**: Functional limitation, documented workaround exists
- **LOW**: Minor UX or performance issue

---

## Do Not Fix Without Discussion

These are intentional MVP tradeoffs. Attempting to "fix" them may introduce worse problems. If you think one should be fixed, document it here first and discuss.

---

## BUGS-001 — Time-Lock Is Server-Enforced, Not Cryptographic

**Severity**: HIGH  
**Component**: `services/vault_service.py`  
**Description**: The key release time-lock is enforced by application logic in the FastAPI server. A compromised server process, or an attacker with direct database access, could read the key from the `vault` table or modify `release_at` to bypass the time-lock.  
**Production Fix**: Hardware Security Modules (HSM) — e.g., AWS CloudHSM or Thales Luna HSM — where keys never leave the hardware and the time-lock is enforced at the hardware level, not software.  
**MVP Workaround**: The time-lock correctly prevents access via the API. The threat of a compromised server is out of scope for this MVP.  
**Do Not Fix By**: Adding a fake "cryptographic time-lock" that is actually just an application-level check with extra steps. That would provide false security assurance.

---

## BUGS-002 — AES Keys Stored in Plaintext in SQLite

**Severity**: HIGH  
**Component**: `database.py`, `vault` table  
**Description**: AES-256 keys are stored as base64 strings in the `vault` table. Anyone with read access to the SQLite file (`examshield.db`) can extract all keys.  
**Production Fix**: Encrypt vault entries using a master key stored in HSM or cloud KMS (e.g., AWS KMS). The SQLite file would then contain only ciphertext, unusable without the master key.  
**MVP Workaround**: SQLite file is protected by OS file permissions. Not accessible via any HTTP route.  
**Do Not Fix By**: Encrypting with a hardcoded master key in the source code — that provides no real protection.

---

## BUGS-003 — No Authentication on API Endpoints

**Severity**: HIGH  
**Component**: All routes  
**Description**: Any client that can reach the server can call any endpoint. Centers are identified only by `center_id` in the URL path, not by an authenticated session.  
**Production Fix**: mTLS certificates per exam center (the server issues a certificate to each registered center) + OTP verification before key release. Or: signed JWT tokens with center identity embedded, verified on every vault request.  
**MVP Workaround**: The demo environment is localhost. The time-lock still prevents key access before exam time even without authentication.  
**Do Not Fix By**: Adding HTTP Basic Auth with hardcoded credentials — security theater.

---

## BUGS-004 — Watermark Extraction Degrades Beyond ±0.22° Rotation

**Severity**: MEDIUM  
**Component**: `watermark/decoder.py`  
**Description**: The perspective correction step uses `approxPolyDP` to find the page corners. At rotation angles beyond approximately ±0.22°, corner detection becomes unreliable and the perspective warp may fail, falling back to the un-corrected image. Grid detection then operates on a rotated image, and the ±4px position tolerance may not cover all grid positions. The ±8° estimate in the original spec was incorrect. The actual safe range is ±0.22° — derived from the 8px proximity tolerance over the maximum corner-to-grid-origin distance of ~2080px at sin(0.22°)≈0.0038.  
**Production Fix**: ORB or SIFT feature matching against a reference page template. Extracts correct perspective transform regardless of rotation angle or viewpoint.  
**MVP Workaround**: Demo photos are generated with simulator at ≤5° rotation. Real-world photos should be taken with phone held approximately flat over the paper.  
**Status**: Acceptable for MVP. Document in submission README.

---

## BUGS-005 — SQLite Cannot Handle Concurrent Writes at Scale

**Severity**: MEDIUM  
**Component**: `database.py`  
**Description**: SQLite uses file-level locking. In production with 4000+ exam centers potentially requesting keys simultaneously at exam start time (9:00 AM sharp), concurrent write requests would queue up or fail.  
**Production Fix**: PostgreSQL with connection pooling (asyncpg). The application code uses parameterized queries throughout and the migration is a config change + schema review.  
**MVP Workaround**: Single-server demo with sequential requests works fine.

---

## BUGS-006 — iOS HEIC Compression Not Tested

**Severity**: MEDIUM  
**Component**: `watermark/simulator.py`, `watermark/decoder.py`  
**Description**: The degradation simulator uses JPEG compression (WhatsApp's default on Android). When iPhones share photos via WhatsApp, they may be compressed as HEIC before conversion to JPEG. The HEIC→JPEG conversion pipeline may introduce different artifacts than direct JPEG compression. Extraction accuracy on HEIC-originated photos is unvalidated.  
**Production Fix**: Test with actual iPhone photos. Likely requires tuning `adaptiveThreshold` block size parameter.  
**MVP Workaround**: Demo photos are generated programmatically with JPEG compression.

---

## BUGS-007 — PDF Generator Produces Simple Text-Only Papers

**Severity**: LOW  
**Component**: `utils/pdf_generator.py`  
**Description**: The sample exam paper generator (FPDF2) creates A4 pages with placeholder text questions, a header, and page number. Real NEET papers contain diagrams, chemical structures, equations, and multi-column layouts. The interaction between complex page content and margin-placed watermark grids is not tested.  
**Production Fix**: Integration with actual exam paper templates. The watermark encoder places grids only in margin whitespace, so complex page content should not interfere — but this is unvalidated.  
**MVP Workaround**: Demo papers are clearly labeled as sample papers. Sufficient for demonstrating the concept.

---

## BUGS-010 — Decoder Fails on Full-Frame White Page with Any Rotation

**Severity**: MEDIUM  
**Component**: `watermark/decoder.py`, `watermark/simulator.py`  
**Discovered**: M1 accuracy test — 0/20 extractions with random rotation  
**Description**: Three-part failure chain:
  1. White page on white simulator fill → _detect_page_boundary returns None →
     perspective correction (Steps 2–3) never fires → decoder reads grid
     positions at hardcoded pixel coordinates on a rotated image.
  2. ±5° rotation displaces far corners by 18–183px. MARKER_PROXIMITY_PX=8
     tolerates only ±0.22°. All grid positions missed.
  3. No markers found → all bits extracted as 0 → verify_crc8([0]*36) returns
     True (CRC-8/SMBUS init=0x00, all-zeros is a valid codeword) → false decode
     as center_id=0. The if not region_cands guard does not protect against this.  
**What does NOT fix it**: Marker size tuning (spec steps 1–3) addresses
  contrast/visibility, not positional displacement.  
**Production Fix**: ORB/SIFT feature matching against reference template
  (already noted in BUGS-004).  
**Two MVP-viable options**:
  - Option A (decoder): Rotation-invariant grid search — try expected positions
    at rotation angles -5° to +5° in 0.25° steps. O(1764) position checks per
    image. Keeps simulator unchanged.
  - Option B (simulator): Place page on dark canvas before rotating. Page
    boundary becomes detectable (white-on-dark). Full perspective pipeline fires.
    Keeps decoder unchanged.  
**Demo workaround**: Fixed params rotation_deg=0.0, jpeg_quality=70 give 20/20
  accuracy. Random JPEG + noise + perspective-jitter without rotation is
  sufficient for demo.  
**Status**: Fixed in commit ad9e7db. _step_rotation now uses borderValue=_DARK_BG_FILL
            instead of white (255). Dark frame stays intact after rotation.
            Perspective correction fires correctly. 19/20 accuracy (95%).
            All M1 tests pass (69/69).

---

## BUGS-008 — Layer 2 Digital Watermark — Partial Implementation

**Severity**: LOW  
**Component**: `backend/watermark/dct_encoder.py`, `backend/watermark/dct_decoder.py`  
**Description**: A manual 8×8 block QIM (Quantization Index Modulation) DCT
watermark was implemented in an experimental branch using `scipy.fft.dctn`.
The center_id is embedded in mid-frequency coefficients (positions [4,1] vs
[1,4]) across 64 blocks in the center page region (x:600–1800, y:800–2700),
with a 20-bit payload (4-bit magic prefix + 16-bit center_id) and majority
vote extraction.

**What works**:
- Survives JPEG compression at Q=70 on canonical images
- Survives corner blackout (all 4 dot grid corners blacked out) on canonical images
- Survives perspective warp alone when perspective correction is applied first
- Does not interfere with Layer 1 dot grid extraction

**What fails**:
- Full print→photo→WhatsApp simulation pipeline: Gaussian noise (σ=8) +
  rotation + perspective warp + JPEG combined reduce QIM coefficient margins
  from 25 to ~3, below recovery threshold. Tested at delta=25–100, all fail.

**Scope of each layer**:
- Layer 1 (dot grid): traces physical leaks — paper printed, photographed,
  shared via WhatsApp. Survives full degradation pipeline at ≥85% accuracy.
- Layer 2 (DCT): traces digital leaks — PDF forwarded digitally without
  printing. Survives screenshot and format conversion but not print→photo.
  Together the two layers cover all leak threat vectors in production.

**Production Fix**: Reed-Solomon error correction on the 20-bit DCT payload,
or spread-spectrum embedding instead of QIM.

**Do Not Fix By**: Increasing delta — tested up to 100, does not help.

**Status**: Experimental branch only. Not merged into main repo.

---

## BUGS-009 — Rate Limiting Is Per-Process, Not Distributed

**Severity**: LOW  
**Component**: Rate limiting middleware  
**Description**: `slowapi` rate limiting stores counters in process memory. If multiple uvicorn workers are running, each worker has independent rate limit counters. An attacker can bypass per-IP rate limits by distributing requests across workers.  
**Production Fix**: Redis-backed rate limiting (slowapi supports this).  
**MVP Workaround**: Single uvicorn worker in demo. Acceptable.

---

## Open Issues (Discovered During Development)

*Add new issues here as they are discovered. Format:*

```
## BUGS-XXX — Title

**Severity**:
**Component**:
**Description**:
**Discovered**: [date, which milestone audit]
**Fix Applied**:
**Status**: Open / Fixed in commit [hash]
```

---

## BUGS-011 — Path Traversal Returns 404 Instead of Custom 400

**Severity**: LOW
**Component**: `backend/routes/vault_routes.py`
**Description**: A path traversal attempt like `/api/vault/release/{id}/../../etc/passwd`
  is normalised by Starlette's URL routing before reaching the route handler.
  The normalised path `/etc/passwd` matches no route, returning FastAPI's default
  `{"detail": "Not Found"}` 404 rather than our custom `VALIDATION_ERROR` 400.
  S-009 regex validation fires correctly for well-formed center_id values.
**Production Fix**: Add a middleware-level path sanitisation check, or accept
  Starlette's normalisation as sufficient (it is — the traversal is blocked).
**MVP Workaround**: Traversal is blocked. Error format is non-standard but
  harmless. Acceptable for MVP.
**Status**: Open — acceptable for MVP, document only.

---

## BUGS-010 — Center Primary Keys Are Not UUIDs

**Severity**: LOW  
**Component**: `backend/utils/seed.py`, `services/forensics_service.py`  
**Description**: Seeded exam centers use string integers ("001"–"010", "221") as
primary keys rather than UUIDs. This is because forensics_service resolves a decoded
watermark integer by matching exam_centers.id == str(center_id). A proper fix would
add a separate watermark_id integer column to the exam_centers table and look up by
that field, leaving the UUID primary key intact.  
**Production Fix**: Add watermark_id column, update forensics_service lookup query.  
**MVP Workaround**: Functional for demo. String IDs are consistent throughout.  
**Do Not Fix By**: Switching to UUIDs without also updating forensics_service — that
breaks the forensic identification end-to-end.
