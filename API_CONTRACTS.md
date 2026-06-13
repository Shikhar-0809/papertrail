# API Contracts

Single source of truth for every endpoint. Both `backend/routes/*.py` and `frontend/src/api.js` are generated against this document. If they ever disagree, fix the code — this document is authoritative.

All endpoints are prefixed with `/api`. All requests and responses are `application/json` unless noted. All datetime fields are ISO 8601 UTC strings.

---

## Error Response Format (Universal)

Every error response — regardless of endpoint — uses this exact structure:

```json
{
  "error": "Human-readable description",
  "code": "MACHINE_READABLE_CODE",
  "detail": "Optional additional context"
}
```

Common codes:
| Code | HTTP Status | Meaning |
|------|-------------|---------|
| `NOT_FOUND` | 404 | Resource does not exist |
| `VALIDATION_ERROR` | 422 | Request body failed Pydantic validation |
| `FILE_TOO_LARGE` | 413 | Upload exceeds 15MB |
| `UNSUPPORTED_MIME` | 415 | File type not allowed |
| `KEY_NOT_YET_AVAILABLE` | 403 | Time-lock has not expired |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Unhandled server error |

---

## Exam Endpoints

### POST /api/exams

Create a new exam.

**Request**:
```json
{
  "name": "NEET-UG 2026",
  "subject": "Physics, Chemistry, Biology",
  "scheduled_at": "2026-06-14T09:00:00Z",
  "center_ids": ["uuid-1", "uuid-2"]
}
```

**Response** `200`:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "NEET-UG 2026",
  "subject": "Physics, Chemistry, Biology",
  "scheduled_at": "2026-06-14T09:00:00Z",
  "key_release_at": "2026-06-14T08:30:00Z",
  "total_centers": 2,
  "status": "draft",
  "created_at": "2026-06-13T10:00:00Z"
}
```

---

### GET /api/exams

List all exams.

**Response** `200`:
```json
{
  "exams": [
    {
      "id": "...",
      "name": "NEET-UG 2026",
      "subject": "...",
      "scheduled_at": "...",
      "key_release_at": "...",
      "total_centers": 10,
      "status": "distributed",
      "created_at": "..."
    }
  ],
  "total": 1
}
```

---

### GET /api/exams/{exam_id}

Get exam details with per-center status.

**Response** `200`:
```json
{
  "id": "...",
  "name": "NEET-UG 2026",
  "subject": "...",
  "scheduled_at": "...",
  "key_release_at": "...",
  "status": "distributed",
  "centers": [
    {
      "center_id": "...",
      "center_code": "NEET-HAZ-221",
      "center_name": "Oasis School Hazaribagh",
      "city": "Hazaribagh",
      "state": "Jharkhand",
      "paper_generated": true,
      "key_released": false,
      "alert_count": 0,
      "status": "normal"
    }
  ]
}
```

`status` per center: `"normal"` | `"flagged"` | `"compromised"`

---

### POST /api/exams/{exam_id}/generate

Generate watermarked + encrypted PDFs for all centers assigned to this exam.

**Request**: No body.

**Response** `200`:
```json
{
  "exam_id": "...",
  "generated": 10,
  "failed": 0,
  "message": "Papers generated and encrypted for 10 centers"
}
```

**Response** `409` if already generated:
```json
{
  "error": "Papers already generated for this exam",
  "code": "ALREADY_GENERATED"
}
```

---

## Vault Endpoints

### GET /api/vault/release/{exam_id}/{center_id}

Request decryption key for a center's exam paper.

**Path params**:
- `exam_id`: UUID string
- `center_id`: UUID string

**Response** `200` (key available):
```json
{
  "key": "base64encodedAES256key==",
  "algorithm": "AES-256-GCM",
  "released_at": "2026-06-14T08:32:11Z"
}
```

**Response** `403` (time-lock active):
```json
{
  "error": "Decryption key not yet available",
  "code": "KEY_NOT_YET_AVAILABLE",
  "detail": "Key releases at 2026-06-14T08:30:00Z. Current time: 2026-06-14T07:43:22Z",
  "release_at": "2026-06-14T08:30:00Z",
  "minutes_remaining": 46
}
```

---

### GET /api/vault/status/{exam_id}

Get key release status for all centers in an exam.

**Response** `200`:
```json
{
  "exam_id": "...",
  "key_release_at": "2026-06-14T08:30:00Z",
  "centers": [
    {
      "center_id": "...",
      "center_code": "NEET-HAZ-221",
      "is_released": false,
      "released_at": null
    }
  ]
}
```

---

## Forensics Endpoints

### POST /api/forensics/analyze

Upload a suspected leaked exam paper photo for watermark extraction.

**Request**: `multipart/form-data`
- Field name: `file`
- Accepted types: `image/jpeg`, `image/png`, `image/webp`
- Max size: 15MB

**Response** `200`:
```json
{
  "report_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "processing"
}
```

Analysis runs asynchronously. Poll `/api/forensics/report/{report_id}` for results.

---

### GET /api/forensics/report/{report_id}

Get forensic analysis result.

**Response** `200` (identified):
```json
{
  "report_id": "...",
  "status": "identified",
  "confidence": 0.973,
  "analysis_ms": 847,
  "grids_detected": 4,
  "grids_valid": 4,
  "center": {
    "id": "...",
    "center_code": "NEET-HAZ-221",
    "name": "Oasis School Hazaribagh",
    "city": "Hazaribagh",
    "state": "Jharkhand",
    "latitude": 23.99,
    "longitude": 85.36
  },
  "exam": {
    "id": "...",
    "name": "NEET-UG 2026"
  },
  "raw_bits": "0000000011011101000000010001XXXXXXXX",
  "created_at": "2026-06-14T09:15:33Z"
}
```

**Response** `200` (inconclusive):
```json
{
  "report_id": "...",
  "status": "inconclusive",
  "confidence": 0.25,
  "analysis_ms": 612,
  "grids_detected": 1,
  "grids_valid": 0,
  "center": null,
  "exam": null,
  "raw_bits": null,
  "message": "Insufficient grid data. Image may be too degraded or not a watermarked paper.",
  "created_at": "..."
}
```

**Response** `200` (processing — not done yet):
```json
{
  "report_id": "...",
  "status": "processing",
  "created_at": "..."
}
```

---

### GET /api/forensics/reports

List all forensic analyses.

**Response** `200`:
```json
{
  "reports": [
    {
      "report_id": "...",
      "status": "identified",
      "confidence": 0.973,
      "center_code": "NEET-HAZ-221",
      "center_name": "Oasis School Hazaribagh",
      "created_at": "..."
    }
  ],
  "total": 1
}
```

---

## Audit Endpoints

### GET /api/audit/log

Full audit log, filterable.

**Query params** (all optional):
- `exam_id`: filter by exam
- `center_id`: filter by center
- `severity`: filter by severity level (`INFO`|`LOW`|`MEDIUM`|`HIGH`|`CRITICAL`)
- `limit`: max results (default 50, max 200)
- `offset`: pagination offset (default 0)

**Response** `200`:
```json
{
  "events": [
    {
      "id": 1,
      "event_type": "key_request",
      "exam_id": "...",
      "center_id": "...",
      "center_code": "NEET-HAZ-221",
      "center_name": "Oasis School Hazaribagh",
      "ip_address": "103.21.88.14",
      "severity": "CRITICAL",
      "rule_id": "R001",
      "details": {
        "minutes_early": 47,
        "action": "key_blocked"
      },
      "human_readable": "Center NEET-HAZ-221 attempted key access 47 minutes early from 103.21.88.14",
      "timestamp": "2026-06-14T07:43:22Z"
    }
  ],
  "total": 47,
  "limit": 50,
  "offset": 0
}
```

---

### GET /api/audit/alerts

Active alerts only (severity HIGH or CRITICAL).

**Response** `200`:
```json
{
  "alerts": [
    {
      "alert_id": "ALR-20260614-0047",
      "rule_id": "R001",
      "severity": "CRITICAL",
      "center_code": "NEET-HAZ-221",
      "center_name": "Oasis School Hazaribagh",
      "triggered_at": "2026-06-14T07:43:22Z",
      "human_readable": "Center NEET-HAZ-221 attempted key access 47 minutes early from 103.21.88.14",
      "action_taken": "key_blocked"
    }
  ],
  "count": 1
}
```

---

## Dashboard Endpoints

### GET /api/dashboard/stats

Summary statistics for the dashboard home page.

**Response** `200`:
```json
{
  "total_exams": 3,
  "total_centers": 10,
  "papers_generated": 10,
  "keys_released": 0,
  "active_alerts": 1,
  "forensic_analyses": 2,
  "leaks_identified": 1
}
```

---

### GET /api/dashboard/timeline

Last 50 audit events for the timeline component.

**Response** `200`:
```json
{
  "events": [
    {
      "id": 47,
      "event_type": "key_denied_premature",
      "center_code": "NEET-HAZ-221",
      "severity": "CRITICAL",
      "human_readable": "Premature key access blocked — NEET-HAZ-221",
      "timestamp": "2026-06-14T07:43:22Z"
    }
  ]
}
```

---

## Frontend API Client (api.js)

All fetch calls must go through this module. No other file makes HTTP requests.

```javascript
const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000'

const handleResponse = async (res) => {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Unknown error' }))
    throw new Error(err.error || `HTTP ${res.status}`)
  }
  return res.json()
}

// Exams
export const getExams = () =>
  fetch(`${BASE_URL}/api/exams`).then(handleResponse)

export const getExam = (examId) =>
  fetch(`${BASE_URL}/api/exams/${examId}`).then(handleResponse)

export const createExam = (data) =>
  fetch(`${BASE_URL}/api/exams`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  }).then(handleResponse)

export const generatePapers = (examId) =>
  fetch(`${BASE_URL}/api/exams/${examId}/generate`, { method: 'POST' }).then(handleResponse)

// Vault
export const releaseKey = (examId, centerId) =>
  fetch(`${BASE_URL}/api/vault/release/${examId}/${centerId}`).then(handleResponse)

// Forensics
export const analyzePhoto = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return fetch(`${BASE_URL}/api/forensics/analyze`, {
    method: 'POST',
    body: formData
  }).then(handleResponse)
}

export const getForensicReport = (reportId) =>
  fetch(`${BASE_URL}/api/forensics/report/${reportId}`).then(handleResponse)

export const getForensicReports = () =>
  fetch(`${BASE_URL}/api/forensics/reports`).then(handleResponse)

// Audit
export const getAuditLog = (params = {}) => {
  const query = new URLSearchParams(params).toString()
  return fetch(`${BASE_URL}/api/audit/log${query ? '?' + query : ''}`).then(handleResponse)
}

export const getAlerts = () =>
  fetch(`${BASE_URL}/api/audit/alerts`).then(handleResponse)

// Dashboard
export const getDashboardStats = () =>
  fetch(`${BASE_URL}/api/dashboard/stats`).then(handleResponse)

export const getTimeline = () =>
  fetch(`${BASE_URL}/api/dashboard/timeline`).then(handleResponse)
```
