import { useState, useEffect, useCallback, useRef } from 'react'
import { getAuditLog, getAlerts } from '../api'

const SEV_CLS = {
  CRITICAL: 'bg-red-900 text-red-300',
  HIGH:     'bg-orange-900 text-orange-300',
  MEDIUM:   'bg-yellow-900 text-yellow-300',
  LOW:      'bg-blue-900 text-blue-300',
  INFO:     'bg-gray-700 text-gray-300',
}

function SevBadge({ s }) {
  return <span className={`text-xs px-2 py-0.5 rounded font-mono ${SEV_CLS[s] ?? SEV_CLS.INFO}`}>{s}</span>
}

export default function AuditTrail() {
  const [events, setEvents]   = useState([])
  const [alerts, setAlerts]   = useState([])
  const [total, setTotal]     = useState(0)
  const [offset, setOffset]   = useState(0)
  const [filter, setFilter]   = useState('')
  const [pending, setPending] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const filterRef             = useRef('')

  const loadData = useCallback(async (sev, off, replace) => {
    const params = {}
    if (sev) params.severity = sev
    if (off > 0) params.offset = off
    const [log, alr] = await Promise.all([
      getAuditLog(params),
      replace ? getAlerts() : Promise.resolve(null),
    ])
    setEvents(prev => replace ? (log.events ?? []) : [...prev, ...(log.events ?? [])])
    setTotal(log.total ?? 0)
    setOffset(off + (log.events?.length ?? 0))
    if (alr) setAlerts(alr.alerts ?? [])
  }, [])

  useEffect(() => {
    setLoading(true)
    loadData('', 0, true).catch(e => setError(e.message)).finally(() => setLoading(false))
    const t = setInterval(() => loadData(filterRef.current, 0, true).catch(() => {}), 60000)
    return () => clearInterval(t)
  }, [loadData])

  const applyFilter = () => {
    filterRef.current = pending
    setFilter(pending); setOffset(0)
    loadData(pending, 0, true).catch(e => setError(e.message))
  }

  const clearFilter = () => {
    filterRef.current = ''; setPending(''); setFilter(''); setOffset(0)
    loadData('', 0, true).catch(e => setError(e.message))
  }

  const formatDate = (str) => {
    if (!str) return '—'
    const d = new Date(str)
    return isNaN(d.getTime()) ? str : d.toLocaleString()
  }

  if (loading) return <div className="p-8 text-gray-400 animate-pulse">Loading audit log…</div>
  if (error)   return <div className="p-8 text-red-400 text-sm">Error: {error}</div>

  return (
    <div className="p-6 space-y-6">
      {/* Filter bar */}
      <div className="flex items-center gap-3">
        <select
          value={pending}
          onChange={e => setPending(e.target.value)}
          className="bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded px-3 py-1.5"
        >
          {['', 'INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map(s => (
            <option key={s} value={s}>{s || 'All severities'}</option>
          ))}
        </select>
        <button onClick={applyFilter} className="text-sm bg-indigo-700 hover:bg-indigo-600 text-white px-4 py-1.5 rounded">
          Apply
        </button>
        {filter && (
          <button onClick={clearFilter} className="text-sm text-gray-400 hover:text-white underline">
            Clear filters
          </button>
        )}
      </div>

      {/* Active alerts */}
      {alerts.length > 0 && (
        <div className="border border-red-700 rounded p-4 space-y-3">
          <h3 className="text-red-400 text-sm font-semibold uppercase tracking-wide">Active Alerts</h3>
          {alerts.map(a => (
            <div key={a.alert_id} className="flex flex-wrap items-start gap-2 text-sm">
              <span className="text-xs font-mono bg-gray-800 px-2 py-0.5 rounded text-gray-400">{a.rule_id}</span>
              <SevBadge s={a.severity} />
              <span className="text-gray-400 font-mono text-xs">{a.center_code}</span>
              <span className="text-gray-300 flex-1 min-w-0">{a.human_readable}</span>
              <span className="text-gray-500 text-xs whitespace-nowrap">{formatDate(a.triggered_at)}</span>
              {a.action_taken && <span className="text-xs text-orange-400">{a.action_taken}</span>}
            </div>
          ))}
        </div>
      )}

      {/* Event log */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="text-xs text-gray-500 uppercase tracking-wide border-b border-gray-700">
              {['#', 'Time', 'Type', 'Center', 'Severity', 'Description'].map(h => (
                <th key={h} className="px-3 pb-2">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.map((ev, i) => (
              <tr key={ev.id} className="border-t border-gray-800 hover:bg-gray-800/50">
                <td className="px-3 py-2 text-gray-600 font-mono text-xs">{i + 1}</td>
                <td className="px-3 py-2 text-gray-400 text-xs whitespace-nowrap">{formatDate(ev.timestamp)}</td>
                <td className="px-3 py-2 text-gray-400 font-mono text-xs">{ev.event_type}</td>
                <td className="px-3 py-2 text-gray-300 text-xs">{ev.center_code || '—'}</td>
                <td className="px-3 py-2"><SevBadge s={ev.severity} /></td>
                <td className="px-3 py-2 text-gray-300 max-w-xs truncate">{ev.human_readable}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {events.length === 0 && (
          <p className="px-3 pt-4 text-gray-500 text-sm">No events found.</p>
        )}
      </div>

      {/* Pagination */}
      {events.length < total && (
        <button
          onClick={() => loadData(filter, offset, false).catch(e => setError(e.message))}
          className="text-sm text-indigo-400 hover:text-indigo-300 underline"
        >
          Load more ({events.length} / {total})
        </button>
      )}
    </div>
  )
}
