# How to Use Claude Project + Cursor for ExamShield

Read this before writing a single line of code.

---

## The Mental Model

You have two AI tools with different jobs:

**Claude Project** = Your senior engineer / technical lead
- You talk to it in natural language
- It understands the full architecture, security posture, and spec
- Use it to: design decisions, debug complex problems, review code, generate the first version of complex logic, ask "is this approach right"
- It has all 7 .md files uploaded as project knowledge

**Cursor** = Your fast coding pair
- Reads `.cursorrules` + the .md files you reference in your prompt
- Use it to: generate boilerplate, implement well-specified functions, write tests, wire up routes
- It works fastest when given a narrow, specific task with a clear spec to implement against

They are not interchangeable. Don't use Cursor for architecture decisions. Don't use Claude Project to generate 300 lines of boilerplate when Cursor can do it in 10 seconds.

---

## Setup: One-Time

### 1. Create the Claude Project

1. Go to claude.ai → Projects → New Project
2. Name it "ExamShield FAR AWAY 2026"
3. In Project Instructions, paste the entire contents of `CLAUDE_PROJECT_PROMPT.md`
4. Upload all 7 .md files as project knowledge:
   - `ARCHITECTURE.md`
   - `WATERMARK_SPEC.md`
   - `SECURITY.md`
   - `SECURITY_AUDIT.md`
   - `CODING_STANDARDS.md`
   - `API_CONTRACTS.md`
   - `BUGS.md`

Now every conversation in this project has full context. You never need to re-explain the architecture.

### 2. Set Up the Codebase

```bash
# Create project directory
mkdir examshield && cd examshield

# Copy the scaffold files into it
cp -r /path/to/scaffold/* .

# Initialize git (commit history is part of submission)
git init
git add ARCHITECTURE.md WATERMARK_SPEC.md SECURITY.md SECURITY_AUDIT.md CODING_STANDARDS.md API_CONTRACTS.md BUGS.md .cursorrules README.md .env.example .gitignore
git commit -m "feat: project structure and documentation scaffolding"

# Create Python environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn aiosqlite pydantic cryptography \
  opencv-python-headless numpy fpdf2 python-magic slowapi \
  python-multipart pytest pytest-asyncio httpx bandit safety
pip freeze > requirements.txt

# Create React frontend
npx create-react-app frontend
cd frontend && npm install tailwindcss recharts axios
cd ..

# Create .env file (never commit this)
echo "EXAMSHIELD_MASTER_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" > .env
echo "EXAMSHIELD_DB_PATH=examshield.db" >> .env
echo "EXAMSHIELD_UPLOADS_DIR=/tmp/examshield_uploads" >> .env
echo "EXAMSHIELD_ALLOWED_ORIGINS=http://localhost:3000" >> .env

git commit -m "chore: python environment and dependencies"
```

### 3. Open in Cursor

```bash
cursor .
```

Cursor will automatically read `.cursorrules` from the project root.

---

## The Build Workflow (Per Module)

Every module follows this exact pattern. Do not skip steps.

### Step 1: Design in Claude Project

Before writing any code, open the Claude Project and ask:

> "I'm about to implement `watermark/encoder.py`. Looking at WATERMARK_SPEC.md and ARCHITECTURE.md, confirm my understanding: the encoder takes a numpy image array, embeds a 6×6 dot grid in 4 corners, returns the modified array. It should NOT do any file I/O. Is there anything in the spec I might miss when implementing this?"

Claude will catch edge cases, remind you of constraints you might miss, and confirm your approach. This costs 2 minutes and saves debugging time.

### Step 2: Generate in Cursor

With Cursor open, create the file and write a prompt at the top as a comment, referencing the spec:

```python
# CURSOR PROMPT:
# Implement watermark/encoder.py exactly as specified in WATERMARK_SPEC.md.
# 
# Key requirements from spec:
# - Function: embed_markers(image: np.ndarray, center_id: int, exam_id: int, page_num: int) -> np.ndarray
# - Bit layout: center_id (16 bits) + exam_id (8 bits) + page_num (4 bits) + CRC-8 (8 bits)
# - Marker: 6x6px solid square, RGB(180,180,180)
# - Grid: 6x6 positions, 20px spacing
# - Placed in all 4 corners: offsets (40,40), (2334,40), (40,3362), (2334,3362)
# - CRC-8 from crc.py (must import, not reimplement)
# - Raises ValueError if center_id > 65535 or < 0
# - Raises ValueError if page_num > 15
# - No file I/O, no logging, no database access
# - Follow CODING_STANDARDS.md: type hints, specific exceptions
```

Then let Cursor generate. Review what it produces.

### Step 3: Review in Claude Project

Paste the generated code into Claude Project:

> "Cursor generated this implementation of encoder.py. Review it against WATERMARK_SPEC.md and SECURITY.md. Flag any issues."

Claude will catch: wrong bit order, missing error handling, security issues, deviations from spec.

### Step 4: Fix and Commit

Apply Claude's feedback in Cursor. Then commit:

```bash
git add backend/watermark/encoder.py
git commit -m "feat(watermark): implement dot grid encoder with CRC-8 error correction"
```

### Step 5: Write Tests (Same Session)

Back in Cursor, immediately write the tests:

```python
# CURSOR PROMPT:
# Write tests/test_watermark_roundtrip.py for the encoder in watermark/encoder.py.
# 
# Required test cases (from WATERMARK_SPEC.md test vectors section):
# 1. test_encoder_decoder_roundtrip_center_221: encode center_id=221, decode, verify
# 2. test_encoder_decoder_roundtrip_center_0: edge case minimum
# 3. test_encoder_decoder_roundtrip_center_65535: edge case maximum  
# 4. test_encoder_rejects_invalid_center_id: center_id=-1, center_id=70000 → ValueError
# 5. test_encoder_rejects_invalid_page_num: page_num=16 → ValueError
# 6. test_crc_detects_single_bit_flip: flip each bit 0-27 individually, verify extraction fails
# 
# Use pytest. Import from backend.watermark.encoder and backend.watermark.decoder.
```

### Step 6: Run and Verify

```bash
python -m pytest tests/test_watermark_roundtrip.py -v
```

All tests must pass before moving to the next module. If they don't, debug in Claude Project.

---

## Milestone-Specific Workflows

### M1 — Hours 0–5: Watermark Engine

Order of files to build:
1. `backend/watermark/crc.py` — CRC-8 only, easiest, validates your bit understanding
2. `backend/watermark/encoder.py` — embed markers
3. `backend/watermark/decoder.py` — extract markers (hardest, most important)
4. `backend/watermark/simulator.py` — degradation pipeline
5. `tests/test_watermark_roundtrip.py` — basic roundtrip
6. `tests/test_watermark_accuracy.py` — 20-run accuracy test

**Decision gate at Hour 5**:
```bash
python -m pytest tests/test_watermark_accuracy.py -v -s
```
Read the output. If accuracy < 85%, ask Claude Project:
> "Accuracy is 72%. Marker size is 6×6px, spacing 20px. What parameter should I adjust first?"

Do NOT proceed to backend until accuracy gate is cleared.

**Commit after M1**:
```bash
git add backend/watermark/ tests/test_watermark*.py
git commit -m "feat(watermark): complete encoder/decoder/simulator with 89% extraction accuracy"
```

Then run M1 security audit:
```bash
python -m pytest tests/test_watermark_edge_cases.py -v
```
Add any findings to BUGS.md.

---

### M2 — Hours 5–14: Backend

Order of files:
1. `backend/config.py`
2. `backend/database.py` + run `python backend/database.py` to create tables
3. `backend/crypto/keygen.py` + `backend/crypto/aes.py`
4. `backend/utils/pdf_generator.py`
5. `backend/services/paper_service.py`
6. `backend/services/vault_service.py`
7. `backend/services/anomaly_service.py`
8. `backend/services/forensics_service.py`
9. `backend/routes/exam_routes.py`, `vault_routes.py`, `forensics_routes.py`, `audit_routes.py`, `dashboard_routes.py`
10. `backend/main.py` — wire everything together
11. `backend/utils/seed.py` — seed 10 centers + sample exam
12. Tests for each service

**Test the backend before touching frontend**:
```bash
# Start server
uvicorn backend.main:app --reload

# Seed data
python -m backend.utils.seed

# Quick smoke test
curl http://localhost:8000/api/exams
curl http://localhost:8000/api/dashboard/stats
```

**Run M2 security audit** (from SECURITY_AUDIT.md):
```bash
grep -rn "except:" backend/ --include="*.py"           # must be 0
grep -rn 'f"SELECT' backend/ --include="*.py"          # must be 0
bandit -r backend/ -ll                                  # fix all MEDIUM+HIGH
safety check -r requirements.txt
```

Fix findings, commit with prefix `security(M2-audit):`.

---

### M3 — Hours 14–26: Frontend

Order of components (priority order — do ForensicsLab first):
1. `frontend/src/api.js` — from API_CONTRACTS.md, copy the template directly
2. `frontend/src/pages/ForensicsLab.jsx` — upload + processing + result (THE DEMO PAGE)
3. `frontend/src/pages/Dashboard.jsx` — stats + timeline + alert banner + India map
4. `frontend/src/pages/AuditTrail.jsx` — filterable log table
5. `frontend/src/pages/ExamManager.jsx` — exam table + create modal

For each page, tell Cursor:
```
# CURSOR PROMPT:
# Implement ForensicsLab.jsx — the forensic analysis page.
# 
# API calls: use analyzePhoto(file) and getForensicReport(reportId) from api.js
# 
# Behavior:
# 1. Drag-and-drop upload zone (or click to select file)
# 2. On upload: call analyzePhoto(), store report_id
# 3. Poll getForensicReport(report_id) every 1.5 seconds while status === "processing"
# 4. Show processing animation with these status messages in sequence:
#    "Loading image..." → "Detecting page boundary..." → "Extracting dot patterns..."
#    → "Decoding bit sequence..." → "Verifying integrity..."
# 5. On status="identified": show ForensicResult component (see below)
# 6. On status="inconclusive": show amber warning with diagnostic info
# 
# ForensicResult display:
# - Red alert banner: "LEAK IDENTIFIED"
# - Center name, center_code, city, state (large, prominent)
# - Confidence meter (0-100%)
# - Analysis time in ms
# - Grids detected / valid (e.g. "4/4 grids valid")
# - Raw bits display (monospace, truncated to 36 chars)
# - "New Analysis" button to reset
# 
# Design: dark theme (#0D1117 background), red (#E53D3D) for identified state
# Tailwind classes only, no inline styles
# No localStorage, no dangerouslySetInnerHTML
```

Run M3 audit after completing all pages (see SECURITY_AUDIT.md M3).

---

### M4 — Hours 26–32: Demo Prep + Recording

```bash
# Generate demo test images
python -m backend.utils.generate_demo_images
# This should produce demo/test_photos/leaked_center_221.jpg
# Verify extraction works on this specific file before recording

python3 -c "
import cv2
import sys
sys.path.insert(0, '.')
from backend.watermark.decoder import extract_center_id
img = cv2.imread('demo/test_photos/leaked_center_221.jpg', cv2.IMREAD_GRAYSCALE)
result = extract_center_id(img)
print(f'Status: {result.status}')
print(f'Center ID: {result.center_id}')
print(f'Confidence: {result.confidence}')
assert result.center_id == 221, 'EXTRACTION FAILED — DO NOT RECORD VIDEO YET'
print('EXTRACTION VERIFIED — ready to record')
"
```

Run M4 attack simulation scenarios from SECURITY_AUDIT.md.

Record the demo only after all scenarios pass and extraction is verified.

---

## Prompt Templates for Claude Project

Use these exact prompts when you're stuck:

**Architecture question**:
> "I need to [X]. According to ARCHITECTURE.md, should this logic go in the service layer or the route? What does the module boundary say about this?"

**Security review**:
> "Here is the code I just wrote: [paste code]. Check it against SECURITY.md. Are there any violations of rules S-001 through S-010?"

**Debug help**:
> "My watermark extraction is returning status='inconclusive' for images where I expect it to find the grid. Here is the decoder output: [paste output]. Here is the image characteristics: rotation was about 4 degrees, JPEG quality 70. What in the extraction pipeline (WATERMARK_SPEC.md steps 1-9) is most likely failing?"

**Test gap**:
> "I've written these test cases for vault_service.py: [paste test file]. Looking at the anomaly rules in ARCHITECTURE.md and the vault flow, what cases am I missing?"

**Commit message**:
> "I just implemented [X feature] and fixed [Y bug]. What should the commit message be?"

---

## Staying On Schedule

Paste this into Claude Project if you feel behind:

> "It is currently [time]. I have [X] hours until the deadline. I've completed: [list]. I haven't started: [list]. Looking at the 36-hour plan, what should I cut, what must I keep, and what order should I work in?"

Claude will give you a realistic ruthless cut list based on what actually matters for the submission.
