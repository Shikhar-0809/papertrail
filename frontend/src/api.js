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
