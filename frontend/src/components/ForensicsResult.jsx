export default function ForensicsResult({ result }) {
  const { status } = result;

  if (status === 'identified') {
    const { center, exam, confidence, grids_detected, grids_valid, analysis_ms } = result;
    return (
      <div className="bg-green-950 border border-green-700 rounded-lg p-5 space-y-3">
        <h3 className="text-green-400 font-semibold text-sm uppercase tracking-wider">
          Source Identified
        </h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-gray-500 text-xs mb-0.5">Center</p>
            <p className="text-white font-bold">{center?.center_code}</p>
            <p className="text-gray-300">{center?.name}</p>
            <p className="text-gray-400 text-xs">{center?.city}, {center?.state}</p>
          </div>
          <div>
            <p className="text-gray-500 text-xs mb-0.5">Exam</p>
            <p className="text-gray-300">{exam?.name || '—'}</p>
            <p className="text-gray-500 text-xs mt-2">Confidence</p>
            <p className="text-green-300 font-bold text-xl">
              {((confidence || 0) * 100).toFixed(1)}%
            </p>
          </div>
        </div>
        <p className="text-xs text-gray-500">
          {grids_valid}/{grids_detected} grids valid · {analysis_ms} ms
        </p>
      </div>
    );
  }

  if (status === 'inconclusive') {
    const { confidence, grids_detected, grids_valid, message } = result;
    return (
      <div className="bg-yellow-950 border border-yellow-700 rounded-lg p-5 space-y-2">
        <h3 className="text-yellow-400 font-semibold text-sm uppercase tracking-wider">
          Inconclusive
        </h3>
        <p className="text-gray-400 text-sm">{message}</p>
        <p className="text-xs text-gray-500">
          {grids_valid}/{grids_detected} grids valid
          · confidence {((confidence || 0) * 100).toFixed(1)}%
        </p>
      </div>
    );
  }

  return (
    <div className="bg-red-950 border border-red-700 rounded-lg p-5 space-y-2">
      <h3 className="text-red-400 font-semibold text-sm uppercase tracking-wider">
        Analysis Failed
      </h3>
      <p className="text-gray-400 text-sm">{result.error_message || 'Unknown error'}</p>
    </div>
  );
}
