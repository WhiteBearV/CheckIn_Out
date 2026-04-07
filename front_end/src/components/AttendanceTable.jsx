function StatusBadge({ status }) {
  if (status === 'IN') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-green-500/10 text-green-600 dark:text-green-400">
        <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
        IN
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-orange-500/10 text-orange-600 dark:text-orange-400">
      <span className="w-1.5 h-1.5 rounded-full bg-orange-500" />
      OUT
    </span>
  )
}

function formatTime(isoString) {
  if (!isoString) return '—'
  return new Date(isoString).toLocaleTimeString('th-TH', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export default function AttendanceTable({ records = [], isLoading }) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (records.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-slate-400 dark:text-slate-500">
        <svg className="w-12 h-12 mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        <p className="text-sm">ยังไม่มีการลงเวลาวันนี้</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-700">
            {['ชื่อ-นามสกุล', 'ตำแหน่ง', 'หน่วยงาน', 'กล้อง', 'เวลา', 'สถานะ'].map(h => (
              <th key={h} className="text-left py-3 px-4 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
          {records.map(r => (
            <tr key={r.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
              <td className="py-3 px-4">
                <div className="font-medium text-slate-800 dark:text-slate-100">
                  {r.name || `${r.prename_th || ''} ${r.per_name || ''} ${r.per_surname || ''}`.trim() || r.per_id}
                </div>
                <div className="text-xs text-slate-400 dark:text-slate-500">{r.per_id}</div>
              </td>
              <td className="py-3 px-4 text-slate-600 dark:text-slate-300 max-w-[180px] truncate">
                {r.posname_th || '—'}
              </td>
              <td className="py-3 px-4 text-slate-600 dark:text-slate-300 max-w-[180px] truncate">
                {r.organize_th || '—'}
              </td>
              <td className="py-3 px-4 text-slate-500 dark:text-slate-400 whitespace-nowrap">
                {r.camera_name || '—'}
              </td>
              <td className="py-3 px-4 text-slate-500 dark:text-slate-400 whitespace-nowrap font-mono text-xs">
                {formatTime(r.check_time)}
              </td>
              <td className="py-3 px-4">
                <StatusBadge status={r.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
