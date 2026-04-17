import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, useEffect, useCallback, useRef } from 'react'
import StatCard from '../components/StatCard'
import AttendanceTable from '../components/AttendanceTable'
import { fetchAttendanceToday } from '../api/attendance'

const REFRESH_INTERVAL  = 30_000
const SCAN_TIMEOUT_SEC  = 10
const STREAM_BASE = import.meta.env.DEV ? 'http://localhost:8001' : ''

/** แปลง "HH:MM:SS" → วินาทีที่ผ่านไปจากตอนนี้ */
function elapsedSec(timeStr) {
  if (!timeStr || timeStr === '-') return 0
  const parts = timeStr.split(':').map(Number)
  if (parts.length < 3 || parts.some(isNaN)) return 0
  const d = new Date()
  d.setHours(parts[0], parts[1], parts[2], 0)
  return Math.max(0, (Date.now() - d.getTime()) / 1000)
}

async function fetchActiveCams() {
  try {
    const r = await fetch(`${STREAM_BASE}/cameras`, { signal: AbortSignal.timeout(2000) })
    if (!r.ok) return []
    const d = await r.json()
    return d.cameras || []
  } catch { return [] }
}

async function fetchCamConfigs() {
  try {
    const r = await fetch(`${STREAM_BASE}/cameras/config`, { signal: AbortSignal.timeout(2000) })
    if (!r.ok) return []
    const d = await r.json()
    return (Array.isArray(d) ? d : d.cameras || [])
  } catch { return [] }
}

async function fetchCamState(camId) {
  try {
    const r = await fetch(`${STREAM_BASE}/state/${camId}`, {
      cache: 'no-store', signal: AbortSignal.timeout(1500),
    })
    if (!r.ok) return null
    return r.json()
  } catch { return null }
}

function isFresh(state) {
  if (!state || !state.ts) return false
  return (Date.now() / 1000 - state.ts) < 5
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function computeStats(records) {
  const inCount  = records.filter(r => r.status === 'IN').length
  const outCount = records.filter(r => r.status === 'OUT').length
  const perIds   = [...new Set(records.map(r => r.per_id))]
  const stillInside = perIds.filter(id => {
    const recs = records.filter(r => r.per_id === id)
    return recs.some(r => r.status === 'IN') && !recs.some(r => r.status === 'OUT')
  }).length
  return { inCount, outCount, stillInside, total: perIds.length }
}

function computeHourly(records) {
  const hours = Array(24).fill(0)
  records.forEach(r => {
    if (r.status === 'IN' && r.check_time)
      hours[new Date(r.check_time).getHours()]++
  })
  return hours
}

function computeDepts(records) {
  const map = {}
  records.filter(r => r.status === 'IN').forEach(r => {
    const d = r.organize_th || '—'
    map[d] = (map[d] || 0) + 1
  })
  return Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 5)
}

// ─── HourlyChart ───────────────────────────────────────────────────────────────

function HourlyChart({ hours }) {
  const max = Math.max(...hours, 1)
  const cur = new Date().getHours()
  return (
    <div>
      <div style={{ height: 72 }}>
        <svg width="100%" height="100%" viewBox="0 0 240 40" preserveAspectRatio="none">
          {hours.map((v, i) => {
            const bw   = 240 / 24
            const x    = i * bw + 0.5
            const w    = bw - 1
            const h    = (v / max) * 34
            const y    = 38 - h
            const fill = i === cur
              ? 'var(--c-accent)'
              : i < cur
              ? 'var(--c-accent-border)'
              : 'var(--c-border)'
            return <rect key={i} x={x} y={y} width={w} height={Math.max(h, 0.5)} fill={fill} />
          })}
          <line x1="0" y1="38.8" x2="240" y2="38.8"
            stroke="var(--c-border)" strokeWidth="0.5" />
        </svg>
      </div>
      <div
        className="flex justify-between font-mono text-[9px] mt-1 px-0.5"
        style={{ color: 'var(--c-text-4)' }}
      >
        {['00','04','08','12','16','20','23'].map(h => <span key={h}>{h}</span>)}
      </div>
    </div>
  )
}

// ─── DeptChart ─────────────────────────────────────────────────────────────────

const DEPT_COLORS = ['#00ffff', '#0089ff', '#a855f7', '#22c55e', '#f97316']

function DeptChart({ depts, total }) {
  if (!depts.length) return (
    <div
      className="h-20 flex items-center justify-center font-mono text-[10px]"
      style={{ color: 'var(--c-text-4)' }}
    >
      ไม่มีข้อมูล
    </div>
  )
  return (
    <div className="space-y-2.5">
      {depts.map(([dept, count], i) => (
        <div key={dept}>
          <div className="flex justify-between items-center mb-0.5">
            <span
              className="font-mono text-[10px] truncate"
              style={{ color: 'var(--c-text-2)', maxWidth: '75%' }}
            >
              {dept}
            </span>
            <span className="font-mono text-[10px]"
              style={{ color: DEPT_COLORS[i % DEPT_COLORS.length] }}>
              {count}
            </span>
          </div>
          <div className="h-0.5 rounded-full" style={{ background: 'var(--c-border)' }}>
            <div
              className="h-0.5 rounded-full transition-all duration-500"
              style={{
                width:      `${(count / (total || 1)) * 100}%`,
                background: DEPT_COLORS[i % DEPT_COLORS.length] + '90',
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── FaceModal ─────────────────────────────────────────────────────────────────

function FaceModal({ src, name, onClose }) {
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.88)' }}
      onClick={onClose}
    >
      <div
        className="relative flex flex-col items-center gap-3"
        onClick={e => e.stopPropagation()}
      >
        <img
          src={src}
          alt={name}
          className="rounded-lg object-cover"
          style={{ maxWidth: '80vw', maxHeight: '70vh', border: '2px solid var(--c-border)' }}
        />
        <p className="font-mono text-sm" style={{ color: 'rgba(255,255,255,0.70)' }}>{name}</p>
        <p className="font-mono text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
          ESC หรือคลิกพื้นหลังเพื่อปิด
        </p>
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 w-7 h-7 rounded-full flex items-center justify-center"
          style={{ background: 'rgba(239,68,68,0.80)', color: '#fff' }}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  )
}

// ─── FaceSnap ──────────────────────────────────────────────────────────────────
// ลองโหลดรูปจากกล้อง active ทีละตัว ถ้า error ข้ามไปตัวถัดไป

// shape: 'square' = สี่เหลี่ยมเต็ม (ใช้ /snapfull/), 'circle' = วงกลม (ใช้ /snap/)
// cacheBust: ตัวเลขที่เปลี่ยนทุก N วิ → บังคับ browser โหลดรูปใหม่
function FaceSnap({ perId, activeCams, size = 32, shape = 'circle', onClick, cacheBust = 0 }) {
  const [idx, setIdx] = useState(0)
  const isSquare = shape === 'square'
  const endpoint = isSquare ? 'snapfull' : 'snap'
  const srcs = activeCams.map(id =>
    `${STREAM_BASE}/${endpoint}/${id}/${encodeURIComponent(perId)}?t=${cacheBust}`
  )
  const initial = (perId[0] || '?').toUpperCase()

  // reset idx เมื่อ cacheBust เปลี่ยน (รูปใหม่)
  useEffect(() => { setIdx(0) }, [cacheBust, perId])

  const placeholder = (
    <div
      className="flex items-center justify-center font-mono flex-shrink-0"
      style={{
        width:        isSquare ? '100%' : size,
        height:       isSquare ? '100%' : size,
        aspectRatio:  isSquare ? '1/1' : undefined,
        background:   'var(--c-bg-deep)',
        color:        'var(--c-text-3)',
        border:       '1px solid var(--c-border)',
        borderRadius: isSquare ? 6 : '50%',
        fontSize:     Math.round((isSquare ? 40 : size) * 0.38),
        cursor:       'default',
      }}
    >
      {initial}
    </div>
  )

  if (!srcs.length || idx >= srcs.length) return placeholder

  return (
    <img
      key={srcs[idx]}
      src={srcs[idx]}
      alt=""
      className="object-cover flex-shrink-0"
      style={{
        width:        isSquare ? '100%' : size,
        height:       isSquare ? '100%' : size,
        aspectRatio:  isSquare ? '1/1' : undefined,
        borderRadius: isSquare ? 6 : '50%',
        border:       '1px solid var(--c-border)',
        cursor:       onClick ? 'zoom-in' : 'default',
      }}
      onError={() => setIdx(i => i + 1)}
      onClick={() => onClick?.(srcs[idx])}
    />
  )
}

// ─── PersonFoundCard — การ์ดบุคคลที่พบในวันนี้ ──────────────────────────────
// person   : ข้อมูลจาก camera state
// camIds   : list ของ cam_id ทุกตัวที่เจอคนนี้
// camNames : map id→name สำหรับแสดง

function PersonFoundCard({ person, perId, camId, camName, onFaceClick, cacheBust }) {
  const elapsed = elapsedSec(person.first_seen)
  const color   = person.checked_out             ? '#f97316'
                : person.checked_in              ? '#22c55e'
                : elapsed > SCAN_TIMEOUT_SEC     ? '#ef4444'
                : '#eab308'
  const status  = person.checked_out             ? 'OUT'
                : person.checked_in              ? 'IN'
                : elapsed > SCAN_TIMEOUT_SEC     ? 'สแกนไม่สำเร็จ'
                : 'กำลังสแกน'

  const displayName = person.display_name || perId

  return (
    <div
      className="rounded overflow-hidden flex-shrink-0"
      style={{
        width:      140,
        background: 'var(--c-bg-card)',
        border:     `1px solid var(--c-border)`,
        borderTop:  `2px solid ${color}`,
      }}
    >
      {/* รูปเต็มเฟรม */}
      <div
        className="w-full overflow-hidden"
        style={{ aspectRatio: '16/9', background: 'var(--c-bg-deep)' }}
      >
        <FaceSnap
          perId={perId}
          activeCams={[camId]}
          shape="square"
          cacheBust={cacheBust}
          onClick={src => onFaceClick?.({ src, name: displayName })}
        />
      </div>

      <div className="p-2 space-y-1">
        <div className="font-mono text-[10px] truncate font-medium"
          style={{ color: 'var(--c-text)' }}>
          {displayName}
        </div>
        <div className="font-mono text-[9px] truncate"
          style={{ color: 'var(--c-accent)' }}>
          📷 {camName || camId}
        </div>
        <div className="flex items-center justify-between">
          <span className="font-mono text-[9px]" style={{ color }}>{status}</span>
          <span className="font-mono text-[9px]" style={{ color: 'var(--c-text-4)' }}>
            {person.first_seen !== '-' ? person.first_seen : '—'}
          </span>
        </div>
      </div>
    </div>
  )
}

// ─── TodayCard ─────────────────────────────────────────────────────────────────

function TodayCard({ record, activeCams, onFaceClick }) {
  const isIn  = record.status === 'IN'
  const color = isIn ? '#22c55e' : '#f97316'
  const name  = record.name
    || `${record.per_name || ''} ${record.per_surname || ''}`.trim()
    || record.per_id

  return (
    <div
      className="flex-shrink-0 w-36 rounded p-3 flex flex-col gap-1.5"
      style={{
        background: 'var(--c-bg-card)',
        border:     '1px solid var(--c-border)',
        borderTop:  `2px solid ${color}`,
      }}
    >
      {/* Face snapshot */}
      <div className="mx-auto">
        <FaceSnap
          perId={record.per_id}
          activeCams={activeCams}
          size={44}
          onClick={src => onFaceClick?.({ src, name })}
        />
      </div>
      <div className="text-center">
        <div className="font-mono text-[10px] truncate leading-tight"
          style={{ color: 'var(--c-text-2)' }}>
          {name}
        </div>
        <div className="font-mono text-[9px] mt-0.5 truncate"
          style={{ color: 'var(--c-text-4)' }}>
          {record.organize_th || '—'}
        </div>
      </div>
      <div
        className="flex items-center justify-between mt-auto pt-1"
        style={{ borderTop: '1px solid var(--c-border-s)' }}
      >
        <span className="font-mono text-[9px]" style={{ color }}>{isIn ? 'IN' : 'OUT'}</span>
        <span className="font-mono text-[9px]" style={{ color: 'var(--c-text-4)' }}>
          {record.check_time
            ? new Date(record.check_time).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
            : '—'}
        </span>
      </div>
    </div>
  )
}

// ─── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [faceModal,  setFaceModal]  = useState(null)
  const [allStates,  setAllStates]  = useState({})
  const [cacheBust,  setCacheBust]  = useState(0)    // เปลี่ยนทุก 3 วิ → force re-fetch รูป
  const openFace  = useCallback(info => setFaceModal(info), [])
  const closeFace = useCallback(() => setFaceModal(null), [])
  const pollRef   = useRef(null)

  const { data = [], isLoading, dataUpdatedAt } = useQuery({
    queryKey:        ['attendance-today'],
    queryFn:         fetchAttendanceToday,
    refetchInterval: REFRESH_INTERVAL,
  })

  // กล้องที่ active อยู่ (list of IDs)
  const { data: activeCams = [] } = useQuery({
    queryKey:        ['active-cams'],
    queryFn:         fetchActiveCams,
    refetchInterval: 5000,
  })

  // camera config → id→name map
  const { data: camConfigList = [] } = useQuery({
    queryKey:        ['cam-configs'],
    queryFn:         fetchCamConfigs,
    refetchInterval: 10_000,
  })
  const camNames = useMemo(() =>
    Object.fromEntries(camConfigList.map(c => [c.id, c.name || c.id]))
  , [camConfigList])

  // Poll camera states ทุก 2 วิ สำหรับ "บุคคลที่พบวันนี้"
  const pollStates = useCallback(async () => {
    if (!activeCams.length) { pollRef.current = setTimeout(pollStates, 1000); return }
    const results = await Promise.allSettled(activeCams.map(id => fetchCamState(id)))
    setAllStates(prev => {
      const next = { ...prev }
      activeCams.forEach((id, i) => {
        const res = results[i]
        if (res.status === 'fulfilled' && res.value && isFresh(res.value))
          next[id] = res.value
        else
          delete next[id]
      })
      return next
    })
    pollRef.current = setTimeout(pollStates, 2000)
  }, [activeCams])

  useEffect(() => {
    pollStates()
    return () => clearTimeout(pollRef.current)
  }, [pollStates])

  // cacheBust ทุก 3 วิ → บังคับ browser โหลดรูปใหม่
  useEffect(() => {
    const t = setInterval(() => setCacheBust(Date.now()), 3000)
    return () => clearInterval(t)
  }, [])

  // แสดง 1 การ์ด ต่อ 1 กล้อง — กล้องเดียวกันเจอคนเดียวกัน = 2 การ์ด
  const livePersons = useMemo(() => {
    const list = []
    activeCams.forEach(camId => {
      const persons = allStates[camId]?.persons
      if (!persons) return
      Object.entries(persons).forEach(([name, p]) => {
        list.push({ camId, name, person: p })
      })
    })
    return list
  }, [allStates, activeCams])

  const stats  = useMemo(() => computeStats(data),  [data])
  const hourly = useMemo(() => computeHourly(data), [data])
  const depts  = useMemo(() => computeDepts(data),  [data])

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString('th-TH', {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      })
    : null

  return (
    <>
    {faceModal && (
      <FaceModal src={faceModal.src} name={faceModal.name} onClose={closeFace} />
    )}
    <div className="p-8 space-y-6 min-h-full">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-end justify-between">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-widest mb-2"
            style={{ color: 'var(--c-accent)' }}>
            Attendance
          </p>
          <h1 className="text-3xl font-light leading-none" style={{ color: 'var(--c-text)' }}>
            Dashboard
          </h1>
          <p className="text-sm mt-2" style={{ color: 'var(--c-text-3)' }}>
            {new Date().toLocaleDateString('th-TH', {
              weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
            })}
          </p>
        </div>

        <div className="flex items-center gap-2 pb-1">
          <span className="relative flex w-1.5 h-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#22c55e] opacity-60" />
            <span className="relative inline-flex rounded-full w-1.5 h-1.5 bg-[#22c55e]" />
          </span>
          <span className="font-mono text-[11px]" style={{ color: 'var(--c-text-3)' }}>
            {lastUpdated ? `updated ${lastUpdated}` : 'loading...'}
          </span>
        </div>
      </div>

      {/* ── Stat cards ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard title="เช็คอินวันนี้"   value={isLoading ? null : stats.inCount}
          subtitle="ครั้งที่บันทึก IN" color="green"
          icon={<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
          </svg>}
        />
        <StatCard title="เช็คเอาท์วันนี้" value={isLoading ? null : stats.outCount}
          subtitle="ครั้งที่บันทึก OUT" color="orange"
          icon={<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>}
        />
        <StatCard title="อยู่ในอาคาร"     value={isLoading ? null : stats.stillInside}
          subtitle="IN แต่ยังไม่ OUT" color="blue"
          icon={<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
          </svg>}
        />
        <StatCard title="พนักงานทั้งหมด"  value={isLoading ? null : stats.total}
          subtitle="คนที่มีการลงเวลา" color="purple"
          icon={<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>}
        />
      </div>

      {/* ── Charts ──────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-5 gap-4">

        {/* Timeline */}
        <div
          className="col-span-3 rounded p-4"
          style={{ background: 'var(--c-bg-card)', border: '1px solid var(--c-border)' }}
        >
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-widest"
                style={{ color: 'var(--c-accent)' }}>
                Timeline
              </p>
              <p className="text-sm font-light mt-0.5" style={{ color: 'var(--c-text-3)' }}>
                การลงเวลาตามช่วงโมง
              </p>
            </div>
            <div className="flex items-center gap-3 font-mono text-[9px]"
              style={{ color: 'var(--c-text-4)' }}>
              <span className="flex items-center gap-1">
                <span className="w-2 h-1.5 rounded-sm" style={{ background: 'var(--c-accent)' }} />
                ชั่วโมงนี้
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-1.5 rounded-sm" style={{ background: 'var(--c-accent-border)' }} />
                ที่ผ่านมา
              </span>
            </div>
          </div>
          <HourlyChart hours={hourly} />
        </div>

        {/* Departments */}
        <div
          className="col-span-2 rounded p-4"
          style={{ background: 'var(--c-bg-card)', border: '1px solid var(--c-border)' }}
        >
          <p className="font-mono text-[10px] uppercase tracking-widest mb-1"
            style={{ color: 'var(--c-accent)' }}>
            Departments
          </p>
          <p className="text-sm font-light mb-3" style={{ color: 'var(--c-text-3)' }}>
            แจกตามหน่วยงาน
          </p>
          <DeptChart depts={depts} total={stats.inCount} />
        </div>
      </div>

      {/* ── บุคคลที่พบในวันนี้ (live จากกล้อง) ─────────────────────────────── */}
      <div
        className="rounded p-4"
        style={{ background: 'var(--c-bg-card)', border: '1px solid var(--c-border)' }}
      >
        <div className="flex items-center gap-3 mb-3">
          <p className="font-mono text-[10px] uppercase tracking-widest"
            style={{ color: 'var(--c-accent)' }}>
            บุคคลที่พบในวันนี้
          </p>
          <span
            className="font-mono text-[10px] px-2 py-0.5 rounded"
            style={{
              background: 'var(--c-bg-app)',
              color:      'var(--c-text-3)',
              border:     '1px solid var(--c-border)',
            }}
          >
            {livePersons.length} คน
          </span>
          <span className="flex items-center gap-1 font-mono text-[10px] ml-auto"
            style={{ color: '#22c55e' }}>
            <span className="w-1 h-1 rounded-full bg-[#22c55e] animate-pulse" />
            LIVE
          </span>
        </div>

        {livePersons.length === 0 ? (
          <div className="flex items-center justify-center h-24 font-mono text-[10px]"
            style={{ color: 'var(--c-text-4)' }}>
            ยังไม่พบใบหน้า
          </div>
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-2">
            {livePersons.map(({ camId, name, person }) => (
              <PersonFoundCard
                key={`${camId}-${name}`}
                perId={name}
                person={person}
                camId={camId}
                camName={camNames[camId] || camId}
                cacheBust={cacheBust}
                onFaceClick={openFace}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── รายชื่อวันนี้ ────────────────────────────────────────────────────── */}
      <div
        className="rounded p-4"
        style={{ background: 'var(--c-bg-card)', border: '1px solid var(--c-border)' }}
      >
        <div className="flex items-center gap-3 mb-3">
          <p className="font-mono text-[10px] uppercase tracking-widest"
            style={{ color: 'var(--c-accent)' }}>
            รายชื่อวันนี้
          </p>
          <span
            className="font-mono text-[10px] px-2 py-0.5 rounded"
            style={{
              background: 'var(--c-bg-app)',
              color:      'var(--c-text-3)',
              border:     '1px solid var(--c-border)',
            }}
          >
            {[...new Set(data.map(r => r.per_id))].length} คน
          </span>
          <span className="flex items-center gap-1 font-mono text-[10px] ml-auto"
            style={{ color: '#22c55e' }}>
            <span className="w-1 h-1 rounded-full bg-[#22c55e] animate-pulse" />
            LIVE
          </span>
        </div>

        {data.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-24 gap-2">
            <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"
              style={{ color: 'var(--c-text-4)' }}>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
                d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <p className="font-mono text-[10px] uppercase tracking-widest"
              style={{ color: 'var(--c-text-4)' }}>
              ยังไม่มีข้อมูล
            </p>
          </div>
        ) : (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {data.map(r => (
              <TodayCard key={r.id} record={r} activeCams={activeCams} onFaceClick={openFace} />
            ))}
          </div>
        )}
      </div>

      {/* ── Attendance Table ─────────────────────────────────────────────────── */}
      <div
        className="rounded"
        style={{ background: 'var(--c-bg-card)', border: '1px solid var(--c-border)' }}
      >
        <div
          className="flex items-center justify-between px-6 py-4"
          style={{ borderBottom: '1px solid var(--c-border)' }}
        >
          <div>
            <p className="font-mono text-[11px] uppercase tracking-widest mb-1"
              style={{ color: 'var(--c-accent)' }}>
              Records
            </p>
            <h2 className="text-base font-light" style={{ color: 'var(--c-text-2)' }}>
              รายการลงเวลาวันนี้
            </h2>
          </div>
          <span
            className="font-mono text-[11px] px-2.5 py-1 rounded"
            style={{
              background: 'var(--c-bg-app)',
              border:     '1px solid var(--c-border)',
              color:      'var(--c-text-3)',
            }}
          >
            {data.length} รายการ
          </span>
        </div>

        <AttendanceTable records={data} isLoading={isLoading} />
      </div>

    </div>
    </>
  )
}
