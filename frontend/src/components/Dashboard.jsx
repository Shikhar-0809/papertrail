import { useState, useEffect, useCallback } from 'react';
import { getDashboardStats, getTimeline, getAlerts } from '../api';

const SEVERITY_CLS = {
  CRITICAL: 'bg-red-900 text-red-300',
  HIGH:     'bg-orange-900 text-orange-300',
  MEDIUM:   'bg-yellow-900 text-yellow-300',
  INFO:     'bg-gray-700 text-gray-400',
};

function SeverityBadge({ level }) {
  const cls = SEVERITY_CLS[level] || SEVERITY_CLS.INFO;
  return (
    <span className={`shrink-0 text-xs px-2 py-0.5 rounded font-mono ${cls}`}>
      {level}
    </span>
  );
}

function StatCard({ label, value, alert }) {
  const isHot = alert && value > 0;
  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold ${isHot ? 'text-red-400' : 'text-white'}`}>
        {value ?? '—'}
        {isHot && (
          <span className="ml-2 text-xs font-medium bg-red-900 text-red-300 px-1.5 py-0.5 rounded">
            !
          </span>
        )}
      </p>
    </div>
  );
}

const formatDate = (str) => {
  if (!str) return '—'
  const d = new Date(str)
  return isNaN(d.getTime()) ? str : d.toLocaleString()
}

function TimelineRow({ event }) {
  const time = formatDate(event.timestamp);
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-gray-700 last:border-0">
      <span className="text-xs text-gray-500 w-20 shrink-0 font-mono pt-0.5">{time}</span>
      <SeverityBadge level={event.severity} />
      <span className="text-sm text-gray-300 min-w-0">{event.human_readable}</span>
    </div>
  );
}

const STAT_DEFS = [
  { key: 'total_exams',        label: 'Total Exams' },
  { key: 'total_centers',      label: 'Total Centers' },
  { key: 'papers_generated',   label: 'Papers Generated' },
  { key: 'keys_released',      label: 'Keys Released' },
  { key: 'active_alerts',      label: 'Active Alerts',      alert: true },
  { key: 'forensic_analyses',  label: 'Forensic Analyses' },
  { key: 'leaks_identified',   label: 'Leaks Identified',   alert: true },
];

export default function Dashboard() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const load = useCallback(async () => {
    try {
      const [stats, timeline, alertsRes] = await Promise.all([
        getDashboardStats(),
        getTimeline(),
        getAlerts(),
      ]);
      setData({ stats, events: timeline.events, alertCount: alertsRes.count ?? 0 });
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  if (loading) {
    return <div className="p-8 text-gray-400 animate-pulse">Loading dashboard…</div>;
  }

  if (error) {
    return (
      <div className="p-8 space-y-3">
        <p className="text-red-400 text-sm">Failed to load: {error}</p>
        <button
          onClick={load}
          className="px-4 py-2 bg-indigo-700 hover:bg-indigo-600 text-white text-sm rounded"
        >
          Retry
        </button>
      </div>
    );
  }

  const { stats, events, alertCount } = data;

  return (
    <div className="p-6 space-y-6">
      {alertCount > 0 && (
        <div className="bg-red-950 border border-red-700 rounded-lg px-4 py-3 text-red-300 text-sm font-medium">
          ⚠ {alertCount} active alert{alertCount !== 1 ? 's' : ''} — check Audit Trail
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-4">
        {STAT_DEFS.map(({ key, label, alert }) => (
          <StatCard key={key} label={label} value={stats[key]} alert={alert} />
        ))}
      </div>

      <div>
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Recent Events
        </h2>
        <div className="bg-gray-800 rounded-lg px-4 py-1 max-h-96 overflow-y-auto">
          {events.length === 0 ? (
            <p className="py-6 text-center text-gray-500 text-sm">No events yet.</p>
          ) : (
            events.map((e) => <TimelineRow key={e.id} event={e} />)
          )}
        </div>
      </div>
    </div>
  );
}
