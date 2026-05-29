import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, useRef } from 'react'
import { fetchHistory, fetchHistoryFilters } from '../api/history'
import { maskPid } from '../utils/pid'

function todayISO() { return new Date().toISOString().slice(0, 10) }
function daysAgoISO(n) {
  const d = new Date(); d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

const PRESETS = [
  { label: 'วันนี้',     from: todayISO(),       to: todayISO() },
  { label: '7 วัน',      from: daysAgoISO(6),    to: todayISO() },
  { label: '14 วัน',     from: daysAgoISO(13),   to: todayISO() },
  { label: 'เดือนนี้',  from: new Date().toISOString().slice(0,7) + '-01', to: todayISO() },
]

// แสดง DD/MM/YYYY บน input type=date — wrapper inline เก็บ value เป็น ISO ตามมาตรฐาน HTML
// แต่ทับ display ด้วย <span> ที่อ่านค่ากลับมาเรียงเป็น DD/MM/YYYY
function DateField({ value, onChange, style }) {
  const ref = useRef(null)
  const display = value
    ? value.slice(8, 10) + '/' + value.slice(5, 7) + '/' + value.slice(0, 4)
    : 'DD/MM/YYYY'
  return (
    <div
      onClick={() => { const el = ref.current; if (el?.showPicker) el.showPicker(); else el?.focus() }}
      style={{
        ...style,
        position: 'relative', display: 'flex', alignItems: 'center', cursor: 'pointer',
      }}
    >
      <span style={{ flex: 1, color: value ? 'var(--c-text)' : 'var(--c-text-4)', userSelect: 'none' }}>
        {display}
      </span>
      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"
        viewBox="0 0 24 24" style={{ color: 'var(--c-text-3)', flexShrink: 0 }}>
        <rect x="3" y="4" width="18" height="18" rx="2" />
        <path d="M16 2v4M8 2v4M3 10h18" strokeLinecap="round" />
      </svg>
      <input
        ref={ref} type="date" value={value || ''} onChange={onChange}
        style={{ position: 'absolute', inset: 0, opacity: 0, pointerEvents: 'none', width: '100%', height: '100%' }}
      />
    </div>
  )
}

function formatThaiDate(iso) {
  if (!iso) return '-'
  try {
    const d = new Date(iso + 'T00:00:00')
    return d.toLocaleDateString('th-TH', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    })
  } catch { return iso }
}

function formatTime(iso) {
  if (!iso || iso.length < 19) return ''
  return iso.slice(11, 19)
}

export default function History() {
  const [from, setFrom]             = useState(daysAgoISO(6))
  const [to, setTo]                 = useState(todayISO())
  const [organize_id, setDept]      = useState('')
  const [per_id, setPerson]         = useState('')
  const [camera_name, setCamera]    = useState('')

  const filtersQ = useQuery({
    queryKey: ['history-filters'],
    queryFn:  fetchHistoryFilters,
    staleTime: 5 * 60_000,
  })

  const historyQ = useQuery({
    queryKey: ['history', from, to, organize_id, per_id, camera_name],
    queryFn:  () => fetchHistory({ from, to, organize_id, per_id, camera_name }),
    keepPreviousData: true,
  })

  const days  = historyQ.data?.days  || []
  const total = historyQ.data?.total || 0

  const inp = {
    fontFamily: 'var(--font-mono)', fontSize: 12, padding: '6px 10px',
    borderRadius: 'var(--radius-sm)', background: 'var(--c-bg-input)',
    border: '1px solid var(--c-border)', color: 'var(--c-text)', outline: 'none',
  }
  const lbl = {
    fontFamily: 'var(--font-mono)', fontSize: 12, textTransform: 'uppercase',
    letterSpacing: '0.08em', color: 'var(--c-text-4)', display: 'block', marginBottom: 4,
  }

  const applyPreset = (p) => { setFrom(p.from); setTo(p.to) }
  const clearFilters = () => {
    setDept(''); setPerson(''); setCamera('')
    setFrom(daysAgoISO(6)); setTo(todayISO())
  }

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      <div className="page-head" style={{ marginBottom: 18 }}>
        <h1 style={{ fontSize: 32, margin: 0 }}>ประวัติลงเวลา</h1>
      </div>

      {/* ── Filters ───────────────────────────────────────── */}
      <div className="panel" style={{ marginBottom: 18 }}>
        <div className="p-head"><span className="eb">FILTERS</span></div>
        <div className="p-body" style={{ display: 'grid', gap: 12 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {PRESETS.map(p => (
              <button key={p.label} className="sys-btn sys-ghost"
                style={{ padding: '12px 24px', fontSize: 24, width: 'auto' }}
                onClick={() => applyPreset(p)}>{p.label}</button>
            ))}
            <button className="btn btn-blue btn-sm"
              style={{ marginLeft: 'auto' }}
              onClick={clearFilters}
              title="รีเซ็ตตัวกรองทั้งหมดกลับเป็นค่าเริ่มต้น (ช่วงวันที่ = 7 วันล่าสุด, แผนก/บุคคล/กล้อง = ทั้งหมด)">
              <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"
                strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 0 0 4.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 0 1-15.357-2m15.357 2H15"/>
              </svg>
              Reset Filter
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
            <div><label style={lbl}>จากวันที่</label>
              <DateField style={inp} value={from} onChange={e => setFrom(e.target.value)} /></div>
            <div><label style={lbl}>ถึงวันที่</label>
              <DateField style={inp} value={to} onChange={e => setTo(e.target.value)} /></div>
            <div><label style={lbl}>แผนก</label>
              <select style={inp} value={organize_id} onChange={e => setDept(e.target.value)}>
                <option value="">ทั้งหมด</option>
                {(filtersQ.data?.departments || []).map(d => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select></div>
            <div><label style={lbl}>บุคคล</label>
              <select style={inp} value={per_id} onChange={e => setPerson(e.target.value)}>
                <option value="">ทั้งหมด</option>
                {(filtersQ.data?.persons || []).map(p => (
                  <option key={p.per_id} value={p.per_id}>{p.name} ({maskPid(p.per_id)})</option>
                ))}
              </select></div>
            <div><label style={lbl}>กล้อง</label>
              <select style={inp} value={camera_name} onChange={e => setCamera(e.target.value)}>
                <option value="">ทั้งหมด</option>
                {(filtersQ.data?.cameras || []).map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select></div>
          </div>

          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--c-text-4)' }}>
            {historyQ.isFetching ? 'กำลังโหลด...' : `พบ ${total} รายการใน ${days.length} วัน`}
          </div>
        </div>
      </div>

      {/* ── Per-day groups ───────────────────────────────────── */}
      {historyQ.isError && (
        <div className="panel" style={{ padding: 14, color: '#ef4444' }}>
          โหลดข้อมูลไม่สำเร็จ — ตรวจ API server (port 8000)
        </div>
      )}

      {!historyQ.isLoading && days.length === 0 && (
        <div className="panel" style={{ padding: 24, textAlign: 'center',
          fontFamily: 'var(--font-mono)', color: 'var(--c-text-4)' }}>
          ไม่มีข้อมูลในช่วงเวลาที่เลือก
        </div>
      )}

      <div style={{ display: 'grid', gap: 14 }}>
        {days.map(day => (
          <DayGroup key={day.date} date={day.date} logs={day.logs} />
        ))}
      </div>
    </div>
  )
}

function DayGroup({ date, logs }) {
  // group logs by per_id เพื่อหา IN/OUT คู่
  const byPerson = useMemo(() => {
    const m = new Map()
    for (const l of logs) {
      const key = l.per_id || l.name
      if (!m.has(key)) m.set(key, { name: l.name, organize_th: l.organize_th, per_id: l.per_id, in: null, out: null, raw: [] })
      const e = m.get(key)
      e.raw.push(l)
      if (l.status === 'IN'  && (!e.in  || l.check_time < e.in.check_time))  e.in  = l
      if (l.status === 'OUT' && (!e.out || l.check_time > e.out.check_time)) e.out = l
    }
    return Array.from(m.values()).sort((a, b) => (a.name || '').localeCompare(b.name || '', 'th'))
  }, [logs])

  return (
    <div className="panel">
      <div className="p-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="eb" style={{ fontSize: 13 }}>{formatThaiDate(date)}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--c-text-4)' }}>
          {byPerson.length} คน · {logs.length} log
        </span>
      </div>
      <div className="p-body" style={{ padding: 0 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          <thead>
            <tr style={{ background: 'var(--c-bg-2)', color: 'var(--c-text-4)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              <th style={th}>ชื่อ-นามสกุล</th>
              <th style={th}>หน่วยงาน</th>
              <th style={th}>เข้า</th>
              <th style={th}>ออก</th>
              <th style={th}>กล้อง</th>
              <th style={{ ...th, textAlign: 'right' }}>logs</th>
            </tr>
          </thead>
          <tbody>
            {byPerson.map(p => (
              <tr key={p.per_id || p.name} style={{ borderTop: '1px solid var(--c-border-s)' }}>
                <td style={td}>
                  <div>{p.name || '-'}</div>
                  {p.per_id && (
                    <div style={{ fontSize: 10, color: 'var(--c-text-4)' }}>{maskPid(p.per_id)}</div>
                  )}
                </td>
                <td style={{ ...td, color: 'var(--c-text-3)' }}>{p.organize_th || '-'}</td>
                <td style={{ ...td, color: p.in ? '#22c55e' : 'var(--c-text-4)' }}>
                  {p.in ? formatTime(p.in.check_time) : '—'}
                </td>
                <td style={{ ...td, color: p.out ? '#f59e0b' : 'var(--c-text-4)' }}>
                  {p.out ? formatTime(p.out.check_time) : '—'}
                </td>
                <td style={{ ...td, color: 'var(--c-text-3)', fontSize: 10 }}>
                  {[p.in?.camera_name, p.out?.camera_name].filter(Boolean).join(' / ') || '-'}
                </td>
                <td style={{ ...td, textAlign: 'right', color: 'var(--c-text-4)' }}>{p.raw.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const th = { padding: '10px 12px', textAlign: 'left', fontWeight: 500, fontSize: 13 }
const td = { padding: '12px', color: 'var(--c-text-2)', verticalAlign: 'top', fontSize: 13 }
