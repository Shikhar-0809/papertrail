import { useState, useEffect } from 'react'
import { getExam, generatePapers, releaseKey } from '../api'

const STATUS_CLS = { draft: 'bg-gray-700 text-gray-300', distributed: 'bg-blue-900 text-blue-300', completed: 'bg-green-900 text-green-300' }
const CENTER_CLS  = { normal: 'bg-gray-700 text-gray-400', flagged: 'bg-yellow-900 text-yellow-300', compromised: 'bg-red-900 text-red-300' }

function CenterRow({ center, examId, keyReleaseAt }) {
  const [keyData, setKeyData]   = useState(null)
  const [keyError, setKeyError] = useState(null)
  const [busy, setBusy]         = useState(false)
  const [copied, setCopied]     = useState(false)

  const handleRelease = async () => {
    setBusy(true)
    setKeyError(null)
    try {
      const data = await releaseKey(examId, center.center_id)
      setKeyData(data)
    } catch (e) {
      const isTimeLock = e.message.toLowerCase().includes('not yet') ||
                         e.message.toLowerCase().includes('time')
      if (isTimeLock) {
        setKeyError(`Not yet available — releases at ${new Date(keyReleaseAt).toLocaleString()}`)
      } else {
        setKeyError(e.message)
      }
    } finally {
      setBusy(false)
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(keyData.key_b64).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <tr className="border-t border-gray-800 text-sm">
      <td className="px-3 py-2 font-mono text-gray-300">{center.center_code}</td>
      <td className="px-3 py-2 text-gray-300">{center.center_name}</td>
      <td className="px-3 py-2 text-gray-400">{center.city}</td>
      <td className="px-3 py-2 text-center">
        {center.paper_generated ? <span className="text-green-400">✓</span> : <span className="text-gray-600">—</span>}
      </td>
      <td className="px-3 py-2 text-center">
        {center.key_released ? <span className="text-green-400">✓</span> : <span className="text-gray-600">—</span>}
      </td>
      <td className="px-3 py-2">
        <span className={`text-xs px-2 py-0.5 rounded ${CENTER_CLS[center.status] || 'bg-gray-700 text-gray-400'}`}>
          {center.status}
        </span>
      </td>
      <td className="px-3 py-2">
        {center.paper_generated && !center.key_released && !keyData && (
          <button
            onClick={handleRelease}
            disabled={busy}
            className="text-xs bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white px-3 py-1 rounded"
          >
            {busy ? 'Releasing…' : 'Release Key'}
          </button>
        )}
        {keyData && (
          <div className="flex items-center gap-2">
            <code className="text-xs text-green-300 font-mono">{keyData.key_b64.slice(0, 16)}…</code>
            <button onClick={handleCopy} className="text-xs text-gray-400 hover:text-white transition-colors">
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
        )}
        {keyError && <span className={`text-xs ${keyError.includes('Not yet') ? 'text-yellow-400' : 'text-red-400'}`}>{keyError}</span>}
      </td>
    </tr>
  )
}

export default function ExamDetail({ examId }) {
  const [exam, setExam]         = useState(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [genState, setGenState] = useState(null)

  useEffect(() => {
    if (!examId) return
    setLoading(true); setError(null); setGenState(null)
    getExam(examId).then((d) => { setExam(d); setLoading(false) })
                   .catch((e) => { setError(e.message); setLoading(false) })
  }, [examId])

  const handleGenerate = async () => {
    setGenState('loading')
    try {
      const res = await generatePapers(examId)
      setGenState({ ok: res.message || `Generated for ${res.generated} centers` })
      getExam(examId).then(setExam)
    } catch (e) {
      setGenState({ error: e.message })
    }
  }

  if (loading) return <div className="p-8 text-gray-400 animate-pulse">Loading…</div>
  if (error)   return <div className="p-8 text-red-400 text-sm">Error: {error}</div>
  if (!exam)   return null

  return (
    <div className="p-6">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="text-xl font-semibold text-white">{exam.name}</h2>
          <p className="text-sm text-gray-400 mt-1">{exam.subject}</p>
        </div>
        <span className={`text-xs px-2 py-1 rounded font-mono ${STATUS_CLS[exam.status] || 'bg-gray-700 text-gray-300'}`}>
          {exam.status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6 text-sm">
        <div>
          <p className="text-gray-500 text-xs uppercase tracking-wide mb-1">Scheduled</p>
          <p className="text-gray-300">{new Date(exam.scheduled_at).toLocaleString()}</p>
        </div>
        <div>
          <p className="text-gray-500 text-xs uppercase tracking-wide mb-1">Key Release</p>
          <p className="text-gray-300">{new Date(exam.key_release_at).toLocaleString()}</p>
        </div>
      </div>

      {exam.status === 'draft' && (
        <div className="mb-6">
          <button
            onClick={handleGenerate}
            disabled={genState === 'loading'}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded"
          >
            {genState === 'loading' ? 'Generating…' : 'Generate Papers'}
          </button>
          {genState?.ok    && <p className="mt-2 text-xs text-green-400">{genState.ok}</p>}
          {genState?.error && <p className="mt-2 text-xs text-red-400">{genState.error}</p>}
        </div>
      )}

      <table className="w-full text-left">
        <thead><tr className="text-xs text-gray-500 uppercase tracking-wide">
          {['Code','Name','City','Paper','Key','Status','Action'].map((h) => <th key={h} className="px-3 pb-2">{h}</th>)}
        </tr></thead>
        <tbody>
          {(exam.centers || []).map((c) => (
            <CenterRow key={c.center_id} center={c} examId={examId} keyReleaseAt={exam.key_release_at} />
          ))}
        </tbody>
      </table>
      {(!exam.centers || exam.centers.length === 0) && (
        <p className="px-3 pt-4 text-sm text-gray-500">No centers assigned.</p>
      )}
    </div>
  )
}
