function StatusBadge({ status }) {
  if (status === 'IN') return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono font-medium"
      style={{ background: 'rgba(34,197,94,0.12)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.25)' }}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse" />
      IN
    </span>
  )
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono font-medium"
      style={{ background: 'rgba(249,115,22,0.12)', color: '#f97316', border: '1px solid rgba(249,115,22,0.25)' }}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-[#f97316]" />
      OUT
    </span>
  )
}

function formatTime(isoString) {
  if (!isoString) return '—'
  return new Date(isoString).toLocaleTimeString('th-TH', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

const TH = ['ชื่อ-นามสกุล', 'ตำแหน่ง', 'หน่วยงาน', 'กล้อง', 'เวลา', 'สถานะ']

export default function AttendanceTable({ records = [], isLoading }) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div
          className="w-6 h-6 rounded-full animate-spin"
          style={{ border: '1px solid var(--c-accent-border)', borderTopColor: 'var(--c-accent)' }}
        />
      </div>
    )
  }

  if (records.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 gap-3">
        <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"
          style={{ color: 'var(--c-text-4)' }}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        <p className="font-mono text-xs uppercase tracking-widest" style={{ color: 'var(--c-text-4)' }}>
          ยังไม่มีการลงเวลา
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr style={{ borderBottom: '1px solid var(--c-border)' }}>
            {TH.map(h => (
              <th
                key={h}
                className="text-left py-3 px-4 font-mono text-[10px] uppercase tracking-widest whitespace-nowrap"
                style={{ color: 'var(--c-text-4)' }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {records.map(r => (
            <tr
              key={r.id}
              className="transition-colors"
              style={{ borderBottom: '1px solid var(--c-border-s)' }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--c-bg-hover)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <td className="py-3 px-4">
                <div className="text-sm leading-tight" style={{ color: 'var(--c-text-2)' }}>
                  {r.name || `${r.prename_th || ''} ${r.per_name || ''} ${r.per_surname || ''}`.trim() || r.per_id}
                </div>
                <div className="font-mono text-[11px] mt-0.5" style={{ color: 'var(--c-text-4)' }}>
                  {r.per_id}
                </div>
              </td>
              <td className="py-3 px-4 max-w-[180px] truncate" style={{ color: 'var(--c-text-2)' }}>
                {r.posname_th || '—'}
              </td>
              <td className="py-3 px-4 max-w-[180px] truncate" style={{ color: 'var(--c-text-2)' }}>
                {r.organize_th || '—'}
              </td>
              <td className="py-3 px-4 font-mono text-xs whitespace-nowrap" style={{ color: 'var(--c-text-3)' }}>
                {r.camera_name || '—'}
              </td>
              <td className="py-3 px-4 font-mono text-xs whitespace-nowrap" style={{ color: 'var(--c-text-2)' }}>
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
