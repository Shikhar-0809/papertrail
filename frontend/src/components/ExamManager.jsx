import { useState, useEffect } from 'react';
import { getExams } from '../api';
import ExamDetail from './ExamDetail';

const STATUS_CLS = {
  draft:       'bg-gray-700 text-gray-300',
  distributed: 'bg-blue-900 text-blue-300',
  completed:   'bg-green-900 text-green-300',
};

function StatusBadge({ status }) {
  const cls = STATUS_CLS[status] || 'bg-gray-700 text-gray-300';
  return <span className={`shrink-0 text-xs px-2 py-0.5 rounded font-mono ${cls}`}>{status}</span>;
}

export default function ExamManager() {
  const [exams, setExams]     = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  useEffect(() => {
    getExams()
      .then((d) => { setExams(d.exams || []); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, []);

  if (loading) return <div className="p-8 text-gray-400 animate-pulse">Loading exams…</div>;
  if (error)   return <div className="p-8 text-red-400 text-sm">Error: {error}</div>;

  return (
    <div className="flex h-full min-h-0" style={{ height: 'calc(100vh - 112px)' }}>
      {/* Exam list */}
      <div className="w-72 shrink-0 border-r border-gray-700 overflow-y-auto">
        {exams.length === 0 && (
          <p className="p-6 text-gray-500 text-sm">No exams yet.</p>
        )}
        {exams.map((exam) => (
          <button
            key={exam.id}
            onClick={() => setSelected(exam.id)}
            className={
              `w-full text-left px-4 py-4 border-b border-gray-800 transition-colors ` +
              `hover:bg-gray-800 ` +
              (selected === exam.id ? 'bg-gray-800 border-l-2 border-l-indigo-500' : '')
            }
          >
            <div className="flex items-start justify-between gap-2 mb-1">
              <p className="text-sm font-medium text-white leading-snug">{exam.name}</p>
              <StatusBadge status={exam.status} />
            </div>
            <p className="text-xs text-gray-500 truncate">{exam.subject}</p>
            <p className="text-xs text-gray-600 mt-1">
              {new Date(exam.scheduled_at).toLocaleDateString()} · {exam.total_centers} centers
            </p>
          </button>
        ))}
      </div>

      {/* Detail panel */}
      <div className="flex-1 overflow-y-auto">
        {selected
          ? <ExamDetail examId={selected} />
          : <p className="p-8 text-gray-500 text-sm">Select an exam to view details.</p>}
      </div>
    </div>
  );
}
