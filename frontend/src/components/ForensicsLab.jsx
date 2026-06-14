import { useState, useEffect, useCallback, useRef } from 'react';
import { analyzePhoto, getForensicReport, getForensicReports } from '../api';
import ForensicsResult from './ForensicsResult';

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

const formatDate = (str) => {
  if (!str) return '—'
  const d = new Date(str)
  return isNaN(d.getTime()) ? str : d.toLocaleString()
}

const STATUS_CLS = {
  identified:   'bg-green-900 text-green-300',
  inconclusive: 'bg-yellow-900 text-yellow-300',
  processing:   'bg-blue-900 text-blue-300',
  failed:       'bg-red-900 text-red-300',
};

function StatusBadge({ status }) {
  const cls = STATUS_CLS[status] || 'bg-gray-700 text-gray-400';
  return <span className={`shrink-0 text-xs px-2 py-0.5 rounded font-mono ${cls}`}>{status}</span>;
}

export default function ForensicsLab() {
  const [file, setFile]       = useState(null);
  const [uploading, setUploading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [result, setResult]   = useState(null);
  const [reports, setReports] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const pollRef  = useRef(null);
  const inputRef = useRef(null);

  const loadReports = useCallback(async () => {
    try {
      const data = await getForensicReports();
      setReports(data.reports || []);
    } catch (_) {}
  }, []);

  useEffect(() => {
    loadReports();
    return () => clearInterval(pollRef.current);
  }, [loadReports]);

  const startPolling = useCallback((reportId) => {
    setPolling(true);
    pollRef.current = setInterval(async () => {
      try {
        const r = await getForensicReport(reportId);
        if (r.status !== 'processing') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setPolling(false);
          setResult(r);
          loadReports();
        }
      } catch (_) {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setPolling(false);
      }
    }, 2000);
  }, [loadReports]);

  const pickFile = (f) => {
    if (!f) return;
    if (!ALLOWED_TYPES.includes(f.type)) {
      alert('Please select a JPEG, PNG, or WebP image.');
      return;
    }
    setFile(f);
    setResult(null);
  };

  const handleAnalyze = async () => {
    if (!file || uploading || polling) return;
    setUploading(true);
    try {
      const { report_id } = await analyzePhoto(file);
      startPolling(report_id);
    } catch (e) {
      setResult({ status: 'failed', error_message: e.message });
    } finally {
      setUploading(false);
    }
  };

  const dropProps = {
    onDragOver:  (e) => { e.preventDefault(); setDragOver(true); },
    onDragLeave: () => setDragOver(false),
    onDrop:      (e) => { e.preventDefault(); setDragOver(false); pickFile(e.dataTransfer.files[0]); },
  };

  const btnLabel = uploading ? 'Uploading…' : polling ? 'Analyzing…' : 'Analyze';

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      {/* Upload panel */}
      <div className="bg-gray-800 rounded-lg p-6 space-y-4">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
          Analyze Leaked Paper
        </h2>
        <div
          {...dropProps}
          onClick={() => inputRef.current?.click()}
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
            dragOver ? 'border-indigo-400 bg-indigo-950/40' : 'border-gray-600 hover:border-gray-400'
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={(e) => pickFile(e.target.files[0])}
          />
          {file ? (
            <p className="text-gray-300 text-sm font-mono">{file.name}</p>
          ) : (
            <p className="text-gray-500 text-sm">
              Drag &amp; drop a photo, or click to select
              <br />
              <span className="text-xs text-gray-600">JPEG · PNG · WebP</span>
            </p>
          )}
        </div>
        <button
          onClick={handleAnalyze}
          disabled={!file || uploading || polling}
          className="px-5 py-2 bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors"
        >
          {btnLabel}
        </button>
      </div>

      {/* Result panel */}
      {result && <ForensicsResult result={result} />}

      {/* History */}
      {reports.length > 0 && (
        <div>
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Analysis History
          </h2>
          <div className="bg-gray-800 rounded-lg divide-y divide-gray-700">
            {reports.map((r) => (
              <div key={r.report_id} className="flex items-center gap-3 px-4 py-3 text-sm">
                <span className="text-gray-500 text-xs font-mono w-24 shrink-0">
                  {formatDate(r.created_at)}
                </span>
                <StatusBadge status={r.status} />
                <span className="text-gray-300 font-mono text-xs">{r.center_code || '—'}</span>
                <span className="text-gray-500 text-xs ml-auto">
                  {r.confidence != null ? `${(r.confidence * 100).toFixed(1)}%` : ''}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
