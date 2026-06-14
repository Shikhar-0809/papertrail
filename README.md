# ExamShield

**Cryptographic exam-paper distribution with forensic leak tracing.**

## What ExamShield Does

High-stakes exams like India's NEET-UG are routinely compromised when printed
question papers leak from exam centers minutes before the test begins — an
insider photographs a paper and forwards it over WhatsApp to an organized
network. Once a paper is out, there is no way to prove *which* of thousands of
centers it came from, so accountability collapses and the leak spreads freely.

ExamShield closes both gaps. Every paper is distributed as an **AES-256-GCM
encrypted** file whose decryption key is held in a **time-locked vault** that
refuses to release it until 30 minutes before the exam — so a paper obtained
early is just ciphertext. Each printed page also carries an invisible **forensic
watermark**: a redundant grid of faint dots in all four margins that encodes the
center ID, exam ID, and a CRC checksum. When a leaked photo surfaces, uploading
it to the Forensics Lab extracts that watermark — surviving print, photography,
rotation, and WhatsApp recompression — and names the source center. Every key
request and anomaly is recorded in an append-only audit trail with real-time
alerts for premature or rapid access attempts.

## Architecture

ExamShield is a single FastAPI application with a React frontend and one SQLite
database — an intentional MVP shape that migrates to PostgreSQL + workers with
config changes, not restructuring. Code is layered with strict downward-only
imports: `routes/` (thin HTTP) → `services/` (business logic + DB) →
`watermark/` and `crypto/` (pure computation, no I/O). The `watermark/` engine
(encoder, decoder, CRC, simulator) and `crypto/` engine (AES-GCM, key
generation) never touch HTTP or the database; services orchestrate them and own
all SQL; routes parse input, call exactly one service, and return a response.
See [`ARCHITECTURE.md`](ARCHITECTURE.md) for module ownership and data flows, and
[`WATERMARK_SPEC.md`](WATERMARK_SPEC.md) for the exact bit layout and extraction
pipeline.

## Setup

```bash
# 1. Clone
git clone <repo-url> examshield && cd examshield

# 2. Backend dependencies (Python 3.11+)
pip install -r requirements.txt

# 3. Configure secrets — copy the template and set a real master key
cp .env.example .env
# Generate a key:  python -c "import secrets; print(secrets.token_hex(32))"
# then set EXAMSHIELD_MASTER_KEY in .env to that 64-char hex string.
# Export it into your shell (or use a dotenv loader):
#   bash/zsh:    export EXAMSHIELD_MASTER_KEY=<hex>
#   PowerShell:  $env:EXAMSHIELD_MASTER_KEY = "<hex>"

# 4. Seed the database (10 centers, 1 exam, encrypted papers, audit history)
python -m backend.utils.seed

# 5. Run the API
uvicorn backend.main:app --reload

# 6. Run the frontend (separate terminal)
cd frontend && npm install && npm start
```

The API serves on `http://localhost:8000`, the frontend on
`http://localhost:3000`. The seed script is idempotent — running it twice
creates no duplicate data.

## Running the Demo

Generate a realistic "leaked paper" photo and self-verify the watermark:

```bash
python backend/utils/generate_demo_photo.py
```

This builds a watermarked A4 page for center **221**, simulates the
print → photograph → WhatsApp degradation pipeline, saves
`demo/test_photos/leaked_center_221.jpg`, then immediately re-decodes the saved
file and exits non-zero if extraction fails. Three demo flows, all visible in
the React UI:

1. **Paper generation** — In *Exam Manager*, open the seeded *NEET-UG 2026*
   exam and use *Generate Papers* (already done by the seed). Each center gets a
   watermarked page that is AES-256-GCM encrypted; the key and ciphertext path
   are stored in the vault.
2. **Time-locked key request** — Request a key for a center before the release
   time (the seeded exam releases tomorrow at 08:30 IST). The vault returns
   **403 KEY_NOT_YET_AVAILABLE** and an **R001 CRITICAL** anomaly fires,
   appearing on the Dashboard alert banner and in the Audit Trail within
   seconds.
3. **Forensic identification** — In *Forensics Lab*, upload
   `demo/test_photos/leaked_center_221.jpg`. ExamShield extracts the watermark
   and reports **center NEET-HAZ-221 identified** with a confidence score and a
   `forensic_match` CRITICAL audit event.

## Running Tests

```bash
# Full existing suite (watermark, CRC, crypto, roundtrip, accuracy)
pytest tests/ -v

# M4 attack scenarios (early access, IDOR, rate limit, tamper, partial grid)
pytest tests/test_m4_integration.py -v

# Self-verifying demo photo generator (exits non-zero if the watermark fails)
python backend/utils/generate_demo_photo.py
```

The M4 integration tests drive the FastAPI app in-process via
`httpx.AsyncClient` (no separate server needed) and each test sets up and tears
down its own data, so they do not depend on the seed.

## Known Limitations

ExamShield is an honest MVP. The following are documented, intentional tradeoffs
(full detail in [`BUGS.md`](BUGS.md)):

- **BUGS-001 (HIGH)** — The key time-lock is enforced by the application server,
  not cryptographically. A compromised server could release keys early.
  Production fix: hardware security module (HSM).
- **BUGS-002 (HIGH)** — AES keys are stored as base64 in SQLite, not encrypted
  at rest. Anyone with read access to the DB file can extract them. Production
  fix: wrap vault entries with a KMS/HSM-held master key.
- **BUGS-003 (HIGH)** — There is no authentication on API endpoints; centers are
  identified only by ID in the URL. Production fix: per-center mTLS or signed
  JWTs with OTP before key release.
- **BUGS-004 (MEDIUM)** — Watermark extraction degrades beyond roughly ±0.22°
  rotation because perspective correction relies on contour-based corner
  detection. Production fix: ORB/SIFT feature matching against a reference
  template. MVP workaround: photograph the page held approximately flat.

These are **not** "fixed" with partial measures that create false security —
e.g., a fake cryptographic time-lock would be worse than an honest
server-enforced one.

## Security Posture

The threat model (see [`SECURITY.md`](SECURITY.md)) is an **insider at an exam
center** with physical access to printed papers and a smartphone, plus a network
attacker observing HTTP traffic. ExamShield's guarantees: a paper obtained
before release time is unusable (AES-256-GCM confidentiality + a server-enforced
time-lock), any modification of the ciphertext is detected (GCM authentication
tag), and a leaked photo can be traced to its source center (redundant,
degradation-resistant watermark). Defensive engineering is enforced throughout:
all configuration and secrets come from the environment and the app fails loudly
if the master key is missing; all SQL is parameterized; AES key values are never
logged; uploads are validated by size and content-sniffed MIME type, saved under
UUID filenames outside any web root; the forensics endpoint is rate-limited; and
HTTP responses never leak stack traces. Out of scope for the MVP: nation-state
attackers, server-host compromise, and side-channel attacks.
