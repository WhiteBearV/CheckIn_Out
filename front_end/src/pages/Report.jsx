import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, useRef } from 'react'
import { fetchReportSummary, fetchHistoryFilters, reportExportUrl } from '../api/history'
import { authFetch } from '../api/client'
import { maskPid } from '../utils/pid'

function todayISO() { return new Date().toISOString().slice(0, 10) }
function daysAgoISO(n) { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10) }

const PRESETS = [
  { label: 'วันนี้',    from: todayISO(),     to: todayISO() },
  { label: '7 วัน',     from: daysAgoISO(6),  to: todayISO() },
  { label: '14 วัน',    from: daysAgoISO(13), to: todayISO() },
  { label: 'เดือนนี้', from: new Date().toISOString().slice(0,7) + '-01', to: todayISO() },
]

// แสดง DD/MM/YYYY บน input type=date — wrapper inline เก็บ value เป็น ISO ตามมาตรฐาน HTML
function DateField({ value, onChange, style }) {
  const ref = useRef(null)
  const display = value
    ? value.slice(8, 10) + '/' + value.slice(5, 7) + '/' + value.slice(0, 4)
    : 'DD/MM/YYYY'
  return (
    <div
      onClick={() => { const el = ref.current; if (el?.showPicker) el.showPicker(); else el?.focus() }}
      style={{ ...style, position: 'relative', display: 'flex', alignItems: 'center', cursor: 'pointer' }}
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

const CAT_COLOR = {
  complete: '#22c55e',  // เขียว — ลงครบ IN+OUT
  in_only:  '#3b82f6',  // น้ำเงิน — เข้าอย่างเดียว
  out_only: '#f59e0b',  // ส้ม — ออกอย่างเดียว
}
const CAT_LABEL = {
  complete: 'ลงครบ (IN+OUT)',
  in_only:  'เข้าอย่างเดียว',
  out_only: 'ออกอย่างเดียว',
}

function PrinterIcon() {
  return (
    <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"
      strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
      <rect x="6" y="14" width="12" height="8" rx="1" />
    </svg>
  )
}

export default function Report() {
  const [from, setFrom]          = useState(daysAgoISO(6))
  const [to, setTo]              = useState(todayISO())
  const [organize_id, setDept]   = useState('')
  const [per_id, setPerson]      = useState('')
  const [camera_name, setCamera] = useState('')

  const filters = { from, to, organize_id, per_id, camera_name }

  const filtersQ = useQuery({
    queryKey: ['history-filters'],
    queryFn:  fetchHistoryFilters,
    staleTime: 5 * 60_000,
  })

  const summaryQ = useQuery({
    queryKey: ['report-summary', from, to, organize_id, per_id, camera_name],
    queryFn:  () => fetchReportSummary(filters),
    keepPreviousData: true,
  })

  const t      = summaryQ.data?.totals  || { complete: 0, in_only: 0, out_only: 0, total_person_days: 0 }
  const byDay  = summaryQ.data?.by_day  || []
  const byDept = summaryQ.data?.by_dept || []
  const items  = summaryQ.data?.items   || []

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
  const handleExport = async (fmt) => {
    const url = reportExportUrl(fmt, filters)
    try {
      const r = await authFetch(url)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const blob = await r.blob()
      const ext  = fmt === 'xlsx' ? 'xlsx' : fmt
      const name = `report_${filters.from}_${filters.to}.${ext}`
      const a    = document.createElement('a')
      a.href     = URL.createObjectURL(blob)
      a.download = name
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      alert(`ส่งออกไม่สำเร็จ: ${e.message}`)
    }
  }

  const total = t.total_person_days || 1
  const pct = (n) => Math.round((n / total) * 100)

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      <div className="page-head" style={{ marginBottom: 18 }}>
        <h1 style={{ fontSize: 32, margin: 0 }}>รายงาน</h1>
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

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn btn-start"
              onClick={() => handleExport('csv')}
              title="ดาวน์โหลดรายงานเป็นไฟล์ CSV (เปิดได้ใน Excel/Google Sheets)">
              <PrinterIcon /> CSV
            </button>
            <button className="btn btn-start"
              onClick={() => handleExport('xlsx')}
              title="ดาวน์โหลดรายงานเป็นไฟล์ Excel (.xlsx)">
              <PrinterIcon /> Excel
            </button>
            <button className="btn btn-start"
              onClick={() => handleExport('pdf')}
              title="ดาวน์โหลดรายงานเป็นไฟล์ PDF">
              <PrinterIcon /> PDF
            </button>
            <button className="btn btn-start"
              onClick={() => handleExport('txt')}
              title="ดาวน์โหลดรายงานเป็นไฟล์ข้อความ (.txt)">
              <PrinterIcon /> TXT
            </button>
            <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 24, color: 'var(--c-text-4)', alignSelf: 'center' }}>
              {summaryQ.isFetching ? 'กำลังโหลด...' : `${t.total_person_days} person-day`}
            </span>
          </div>
        </div>
      </div>

      {/* ── Stat cards ───────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 18 }}>
        <StatBox label="ลงครบ (IN+OUT)" value={t.complete} pct={pct(t.complete)} color={CAT_COLOR.complete} />
        <StatBox label="เข้าอย่างเดียว" value={t.in_only}  pct={pct(t.in_only)}  color={CAT_COLOR.in_only} />
        <StatBox label="ออกอย่างเดียว" value={t.out_only} pct={pct(t.out_only)} color={CAT_COLOR.out_only} />
        <StatBox label="รวม person-day" value={t.total_person_days} pct={100} color="var(--c-accent)" />
      </div>

      {/* ── Bar chart by day ───────────────────────────── */}
      <div className="panel" style={{ marginBottom: 18 }}>
        <div className="p-head"><span className="eb">BY DAY</span></div>
        <div className="p-body">
          {byDay.length === 0 ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--c-text-4)', textAlign: 'center', padding: 12 }}>
              ไม่มีข้อมูล
            </div>
          ) : (
            <StackedBars data={byDay} keyField="date" />
          )}
        </div>
      </div>

      {/* ── Bar chart by dept ──────────────────────────── */}
      <div className="panel" style={{ marginBottom: 18 }}>
        <div className="p-head"><span className="eb">BY DEPARTMENT</span></div>
        <div className="p-body">
          {byDept.length === 0 ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--c-text-4)', textAlign: 'center', padding: 12 }}>
              ไม่มีข้อมูล
            </div>
          ) : (
            <StackedBars data={byDept} keyField="organize_th" />
          )}
        </div>
      </div>

      {/* ── Detail table ───────────────────────────────── */}
      <div className="panel">
        <div className="p-head"><span className="eb">รายละเอียด ({items.length} แถว)</span></div>
        <div className="p-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            <thead>
              <tr style={{ background: 'var(--c-bg-2)', color: 'var(--c-text-4)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                <th style={th}>วันที่</th>
                <th style={th}>ชื่อ</th>
                <th style={th}>หน่วยงาน</th>
                <th style={th}>IN</th>
                <th style={th}>OUT</th>
                <th style={th}>สถานะ</th>
                <th style={{ ...th, textAlign: 'right' }}>logs</th>
              </tr>
            </thead>
            <tbody>
              {items.slice(0, 500).map((r, i) => (
                <tr key={i} style={{ borderTop: '1px solid var(--c-border-s)' }}>
                  <td style={td}>{r.date}</td>
                  <td style={td}>{r.name || '-'}</td>
                  <td style={{ ...td, color: 'var(--c-text-3)' }}>{r.organize_th || '-'}</td>
                  <td style={{ ...td, color: r.has_in ? '#22c55e' : 'var(--c-text-4)' }}>{r.has_in ? '✓' : '—'}</td>
                  <td style={{ ...td, color: r.has_out ? '#f59e0b' : 'var(--c-text-4)' }}>{r.has_out ? '✓' : '—'}</td>
                  <td style={{ ...td, color: CAT_COLOR[r.category] }}>{CAT_LABEL[r.category]}</td>
                  <td style={{ ...td, textAlign: 'right', color: 'var(--c-text-4)' }}>{r.n_logs}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length > 500 && (
            <div style={{ padding: 10, textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-4)' }}>
              แสดง 500 แถวแรก — ส่งออกไฟล์เพื่อดูทั้งหมด
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StatBox({ label, value, pct, color }) {
  return (
    <div className="panel" style={{ padding: 14 }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--c-text-4)', marginBottom: 6 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 28, color, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-4)', marginTop: 4 }}>{pct}%</div>
    </div>
  )
}

function StackedBars({ data, keyField }) {
  const max = Math.max(1, ...data.map(d => (d.complete || 0) + (d.in_only || 0) + (d.out_only || 0)))
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {data.map((d, i) => {
        const total = (d.complete || 0) + (d.in_only || 0) + (d.out_only || 0)
        const w = (n) => ((n || 0) / max) * 100
        return (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '160px 1fr 60px', alignItems: 'center', gap: 8 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--c-text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d[keyField] || '—'}</div>
            <div style={{ display: 'flex', height: 18, background: 'var(--c-bg-2)', borderRadius: 4, overflow: 'hidden' }}>
              <div title={`ลงครบ ${d.complete}`} style={{ width: `${w(d.complete)}%`, background: CAT_COLOR.complete }} />
              <div title={`เข้าอย่างเดียว ${d.in_only}`} style={{ width: `${w(d.in_only)}%`, background: CAT_COLOR.in_only }} />
              <div title={`ออกอย่างเดียว ${d.out_only}`} style={{ width: `${w(d.out_only)}%`, background: CAT_COLOR.out_only }} />
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--c-text-3)', textAlign: 'right' }}>{total}</div>
          </div>
        )
      })}
      {/* legend */}
      <div style={{ display: 'flex', gap: 14, marginTop: 8, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-4)' }}>
        {Object.entries(CAT_LABEL).map(([k, v]) => (
          <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 10, height: 10, background: CAT_COLOR[k], borderRadius: 2, display: 'inline-block' }} />
            {v}
          </span>
        ))}
      </div>
    </div>
  )
}

const th = { padding: '8px 12px', textAlign: 'left', fontWeight: 500 }
const td = { padding: '10px 12px', color: 'var(--c-text-2)', verticalAlign: 'top' }
