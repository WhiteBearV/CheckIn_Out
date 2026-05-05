import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, useEffect, useCallback, useRef } from 'react'
import StatCard from '../components/StatCard'
import AttendanceTable from '../components/AttendanceTable'
import { fetchAttendanceToday, fetchPerson } from '../api/attendance'
import { maskPid } from '../utils/pid'

const REFRESH_INTERVAL  = 30_000
const SCAN_TIMEOUT_SEC  = 10
const STREAM_BASE = import.meta.env.DEV ? 'http://localhost:8001' : ''

// ─── localStorage persistence สำหรับ "บุคคลที่พบวันนี้" ────────────────────
// เก็บรายชื่อที่เจอวันนี้ไว้ แม้กด Stop ก็ยังแสดงต่อ — จะล้างเมื่อเปลี่ยนวันเท่านั้น
const PERSONS_STORAGE_KEY = 'dashboard-persons-today'

function getTodayKey() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

function loadPersistedPersons() {
  try {
    const raw = localStorage.getItem(PERSONS_STORAGE_KEY)
    if (!raw) return {}
    const { date, persons } = JSON.parse(raw)
    if (date !== getTodayKey()) {
      localStorage.removeItem(PERSONS_STORAGE_KEY)
      return {}
    }
    return persons || {}
  } catch {
    return {}
  }
}

function savePersistedPersons(persons) {
  try {
    localStorage.setItem(PERSONS_STORAGE_KEY, JSON.stringify({
      date: getTodayKey(), persons,
    }))
  } catch {}
}

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
  return (Date.now() / 1000 - state.ts) < 8
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

const DEPT_COLORS = ['#22c55e', '#0089ff', '#a855f7', '#f97316', '#eab308']

function DeptChart({ depts, total }) {
  if (!depts.length) return (
    <div className="flex items-center justify-center font-mono text-[10px]"
      style={{ height: 80, color: 'var(--c-text-4)' }}>
      ไม่มีข้อมูล
    </div>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {depts.map(([dept, count], i) => (
        <div className="dept-row" key={dept}>
          <div className="dept-top">
            <span className="dept-name">{dept}</span>
            <span className="dept-count" style={{ color: DEPT_COLORS[i % DEPT_COLORS.length] }}>{count}</span>
          </div>
          <div className="track">
            <div className="fill" style={{
              width: `${(count / (total || 1)) * 100}%`,
              background: DEPT_COLORS[i % DEPT_COLORS.length],
            }} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── FaceModal ─────────────────────────────────────────────────────────────────

function FaceModal({ src, name, organize, posname, onClose }) {
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
        className="relative flex flex-col items-center gap-2"
        onClick={e => e.stopPropagation()}
      >
        <img
          src={src}
          alt={name}
          className="rounded-lg object-cover"
          style={{ maxWidth: '80vw', maxHeight: '70vh', border: '2px solid var(--c-border)' }}
        />
        <p className="font-mono text-base" style={{ color: 'rgba(255,255,255,0.85)', fontWeight: 600 }}>
          {name}
        </p>
        {organize && (
          <p className="font-mono text-xs" style={{ color: 'rgba(255,255,255,0.65)' }}>
            🏢 {organize}
          </p>
        )}
        {posname && (
          <p className="font-mono text-xs" style={{ color: 'rgba(255,255,255,0.50)' }}>
            ▸ {posname}
          </p>
        )}
        <p className="font-mono text-[10px] mt-1" style={{ color: 'rgba(255,255,255,0.25)' }}>
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
function FaceSnap({ perId, displayName, activeCams, size = 32, shape = 'circle', onClick, cacheBust = 0 }) {
  const [idx, setIdx] = useState(0)
  const isSquare = shape === 'square'
  const endpoint = isSquare ? 'snapfull' : 'snap'  // square = full frame, circle = face crop
  const srcs = activeCams.map(id =>
    `${STREAM_BASE}/${endpoint}/${id}/${encodeURIComponent(perId)}?t=${cacheBust}`
  )
  // initial fallback — perId อาจเป็น masked ("*********6666") → first char = "*"
  // จึงใช้ displayName ก่อน (ชื่อจริง) ถ้าไม่มีค่อย fall ไป perId
  const initSrc = displayName?.trim() || perId
  const initial = (initSrc[0] || '?').toUpperCase()

  // reset idx เมื่อ cacheBust เปลี่ยน (รูปใหม่)
  useEffect(() => { setIdx(0) }, [cacheBust, perId])

  const placeholder = (
    <div
      className="flex items-center justify-center font-mono flex-shrink-0"
      style={{
        width:        isSquare ? '100%' : size,
        height:       isSquare ? '100%' : size,
        background:   'var(--c-bg-deep)',
        color:        'var(--c-text-3)',
        border:       '1px solid var(--c-border)',
        borderRadius: isSquare ? 6 : '50%',
        fontSize:     isSquare ? 20 : Math.round(size * 0.38),
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

  // ดึง organize_th / posname_th จาก External API ผ่าน backend (cache 10 นาที)
  const { data: personInfo } = useQuery({
    queryKey: ['person', perId],
    queryFn:  () => fetchPerson(perId),
    enabled:  !!perId,
    staleTime: 10 * 60 * 1000,
  })
  const organize = personInfo?.organize_th || person.organize_th || ''
  const posname  = personInfo?.posname_th  || ''

  return (
    <div
      className="rounded overflow-hidden flex-shrink-0"
      style={{
        width:      170,
        background: 'var(--c-bg-card)',
        border:     `1px solid var(--c-border)`,
        borderTop:  `2px solid ${color}`,
      }}
    >
      {/* รูปเต็มเฟรม */}
      <div
        style={{
          width: '100%', height: 96,
          overflow: 'hidden', position: 'relative',
          background: 'var(--c-bg-deep)',
          borderRadius: '6px 6px 0 0',
        }}
      >
        <FaceSnap
          perId={perId}
          displayName={displayName}
          activeCams={[camId]}
          shape="square"
          cacheBust={cacheBust}
          onClick={src => onFaceClick?.({ src, name: displayName, organize, posname })}
        />
      </div>

      <div className="p-2 space-y-1">
        <div className="font-mono text-[10px] truncate font-medium"
          style={{ color: 'var(--c-text)' }}
          title={displayName}>
          {displayName}
        </div>

        {/* หน่วยงาน / กอง */}
        <div className="font-mono text-[9px] truncate"
          style={{ color: 'var(--c-text-3)' }}
          title={organize || '—'}>
          🏢 {organize || '—'}
        </div>

        {/* ตำแหน่ง — ถ้ามี */}
        {posname && (
          <div className="font-mono text-[9px] truncate"
            style={{ color: 'var(--c-text-4)' }}
            title={posname}>
            ▸ {posname}
          </div>
        )}

        <div className="font-mono text-[9px] truncate"
          style={{ color: 'var(--c-accent)' }}>
          📷 {camName || camId}
        </div>
        <div className="flex items-center justify-between">
          <span className="font-mono text-[9px]" style={{ color }}>{status}</span>
          <span className="font-mono text-[9px]" style={{ color: 'var(--c-text-4)' }}>
            {person.first_seen && person.first_seen !== '-' ? person.first_seen.slice(0, 5) : '—'}
          </span>
        </div>
        {person.last_seen && person.last_seen !== '-' && (
          <div className="flex items-center justify-between">
            <span className="font-mono text-[9px]" style={{ color: 'var(--c-text-4)' }}>พบล่าสุด</span>
            <span className="font-mono text-[9px]" style={{ color: 'var(--c-text-3)' }}>
              {person.last_seen.slice(0, 5)}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── TodayCard — รวม IN + OUT ของคนเดียวในการ์ดเดียว ───────────────────────

function TodayCard({ entry, onFaceClick }) {
  const { per_id, name, organize_th, in: inRec, out: outRec } = entry

  // ดึงรูปจาก External API ผ่าน backend (/person/{per_id}) — ไม่พึ่งไฟล์ในเครื่อง
  const { data: personInfo } = useQuery({
    queryKey: ['person', per_id],
    queryFn:  () => fetchPerson(per_id),
    enabled:  !!per_id,
    staleTime: 10 * 60 * 1000,
  })
  const photoUrl = personInfo?.per_picpath || ''
  const [imgFailed, setImgFailed] = useState(false)
  useEffect(() => { setImgFailed(false) }, [photoUrl])

  const hasPhoto = photoUrl && !imgFailed
  const initial  = (name?.[0] || '?').toUpperCase()

  const fmt = iso => iso
    ? new Date(iso).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
    : '—'

  // ขอบบน: ถ้ามี OUT แล้ว = ส้ม, ถ้ามีแค่ IN = เขียว
  const borderColor = outRec ? '#f97316' : '#22c55e'

  return (
    <div
      className="flex-shrink-0 rounded flex flex-col gap-2"
      style={{
        width: 200, padding: 10,
        background: 'var(--c-bg-card)',
        border:     '1px solid var(--c-border)',
        borderTop:  `2px solid ${borderColor}`,
      }}
    >
      <div className="flex gap-2 items-center" style={{ minWidth: 0 }}>
        <div
          onClick={hasPhoto ? () => onFaceClick?.({
            src: photoUrl, name,
            organize: personInfo?.organize_th || organize_th,
            posname:  personInfo?.posname_th  || '',
          }) : undefined}
          style={{
            width: 44, height: 44, borderRadius: 6, overflow: 'hidden', flexShrink: 0,
            background: 'var(--c-bg-deep)',
            border: '1px solid var(--c-border-s)',
            cursor: hasPhoto ? 'zoom-in' : 'default',
          }}
        >
          {hasPhoto ? (
            <img
              src={photoUrl}
              alt=""
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
              onError={() => setImgFailed(true)}
            />
          ) : (
            <div style={{
              width: '100%', height: '100%', display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600,
              color: 'var(--c-text-3)',
            }}>{initial}</div>
          )}
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="font-mono text-[11px] truncate leading-tight"
            style={{ color: 'var(--c-text-2)' }}>
            {name}
          </div>
          <div className="font-mono text-[9px] truncate mt-0.5"
            style={{ color: 'var(--c-text-4)' }}>
            {organize_th || '—'}
          </div>
          <div className="font-mono text-[9px] truncate"
            style={{ color: 'var(--c-text-4)', opacity: 0.6 }}>
            {maskPid(per_id)}
          </div>
        </div>
      </div>

      <div
        className="flex flex-col gap-1 pt-1.5"
        style={{ borderTop: '1px solid var(--c-border-s)', fontFamily: 'var(--font-mono)', fontSize: 10 }}
      >
        <div className="flex items-center gap-2">
          <span style={{ color: inRec ? '#22c55e' : 'var(--c-text-4)', fontWeight: 600, width: 26 }}>IN</span>
          <span style={{ color: 'var(--c-text-2)', minWidth: 34 }}>{fmt(inRec?.check_time)}</span>
          <span className="truncate" style={{ color: 'var(--c-text-4)', flex: 1, textAlign: 'right' }}>
            📷 {inRec?.camera_name || '—'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span style={{ color: outRec ? '#f97316' : 'var(--c-text-4)', fontWeight: 600, width: 26 }}>OUT</span>
          <span style={{ color: 'var(--c-text-2)', minWidth: 34 }}>{fmt(outRec?.check_time)}</span>
          <span className="truncate" style={{ color: 'var(--c-text-4)', flex: 1, textAlign: 'right' }}>
            📷 {outRec?.camera_name || '—'}
          </span>
        </div>
      </div>
    </div>
  )
}

// ─── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [faceModal,  setFaceModal]  = useState(null)
  const [allStates,  setAllStates]  = useState({})
  const [cacheBust,  setCacheBust]  = useState(0)    // เปลี่ยนทุก 3 วิ → force re-fetch รูป
  // persist รายชื่อที่เจอวันนี้ (persistent ข้าม Stop/refresh, ล้างเมื่อเปลี่ยนวัน)
  const [persistedPersons, setPersistedPersons] = useState(() => loadPersistedPersons())
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

  // merge live state → persistedPersons (เก็บสะสมในวันนั้น)
  useEffect(() => {
    setPersistedPersons(prev => {
      let changed = false
      const next = { ...prev }
      activeCams.forEach(camId => {
        const persons = allStates[camId]?.persons
        if (!persons) return
        Object.entries(persons).forEach(([name, p]) => {
          next[`${camId}|${name}`] = { camId, name, person: p }
          changed = true
        })
      })
      if (!changed) return prev
      savePersistedPersons(next)
      return next
    })
  }, [allStates, activeCams])

  // เช็ค day rollover ทุกนาที → ล้างเมื่อข้ามวัน
  useEffect(() => {
    const check = () => {
      try {
        const raw = localStorage.getItem(PERSONS_STORAGE_KEY)
        if (!raw) return
        const { date } = JSON.parse(raw)
        if (date !== getTodayKey()) {
          localStorage.removeItem(PERSONS_STORAGE_KEY)
          setPersistedPersons({})
        }
      } catch { /* ignore parse errors */ }
    }
    const t = setInterval(check, 60_000)
    return () => clearInterval(t)
  }, [])

  // แสดง 1 การ์ด ต่อ (กล้อง × คน) — persist ข้าม Stop, ล้างเมื่อเปลี่ยนวัน
  const livePersons = useMemo(() => Object.values(persistedPersons), [persistedPersons])

  const stats  = useMemo(() => computeStats(data),  [data])
  const hourly = useMemo(() => computeHourly(data), [data])
  const depts  = useMemo(() => computeDepts(data),  [data])

  // รวม records ของคนเดียวกัน (IN + OUT) เป็น entry เดียว
  const todayEntries = useMemo(() => {
    const map = new Map()
    data.forEach(r => {
      const e = map.get(r.per_id) || { per_id: r.per_id }
      if (r.status === 'IN')  e.in  = r
      if (r.status === 'OUT') e.out = r
      e.name = e.name
        || r.name
        || `${r.per_name || ''} ${r.per_surname || ''}`.trim()
        || r.per_id
      e.organize_th = e.organize_th || r.organize_th
      map.set(r.per_id, e)
    })
    // เรียงตามเวลาล่าสุด (OUT ถ้ามี, ไม่งั้น IN) — คนที่เพิ่งทำล่าสุดอยู่หน้าสุด
    return [...map.values()].sort((a, b) => {
      const ta = new Date(a.out?.check_time || a.in?.check_time || 0).getTime()
      const tb = new Date(b.out?.check_time || b.in?.check_time || 0).getTime()
      return tb - ta
    })
  }, [data])

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString('th-TH', {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      })
    : null

  return (
    <>
    {faceModal && (
      <FaceModal src={faceModal.src} name={faceModal.name}
        organize={faceModal.organize} posname={faceModal.posname}
        onClose={closeFace} />
    )}
    <div className="page">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="page-head">
        <div>
          <div className="eb" style={{ marginBottom: 6 }}>DASHBOARD · TODAY</div>
          <div className="h1">Dashboard</div>
          <div className="sub">
            {new Date().toLocaleDateString('th-TH', {
              weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
            })}
          </div>
        </div>
        <div className="status">
          <span className="dot" />
          {lastUpdated ? `updated ${lastUpdated}` : 'loading...'}
        </div>
      </div>

      {/* ── Stat cards ──────────────────────────────────────────────────────── */}
      <div className="stats">
        <StatCard title="เช็คอินวันนี้"   value={isLoading ? null : stats.inCount}
          subtitle="วันนี้" color="#22c55e"
          icon={<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
          </svg>}
        />
        <StatCard title="เช็คเอาท์วันนี้" value={isLoading ? null : stats.outCount}
          subtitle="ออกแล้ว" color="#f97316"
          icon={<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>}
        />
        <StatCard title="อยู่ในอาคาร"     value={isLoading ? null : stats.stillInside}
          subtitle="ยังอยู่ในอาคาร" color="#0089ff"
          icon={<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
          </svg>}
        />
        <StatCard title="พนักงานทั้งหมด"  value={isLoading ? null : stats.total}
          subtitle="คนที่มีการลงเวลา" color="#a855f7"
          icon={<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>}
        />
      </div>

      {/* ── Charts ──────────────────────────────────────────────────────────── */}
      <div className="two-col" style={{ gridTemplateColumns: '1fr 300px' }}>
        <div className="panel">
          <div className="p-head">
            <span className="eb">TIMELINE · HOURLY</span>
            <span className="eb eb-muted">ชั่วโมงนี้</span>
          </div>
          <div className="p-body" style={{ padding: '18px 20px' }}>
            <HourlyChart hours={hourly} />
          </div>
        </div>
        <div className="panel">
          <div className="p-head">
            <span className="eb">DEPARTMENTS</span>
            <span className="eb eb-muted">top 5</span>
          </div>
          <div className="p-body">
            <DeptChart depts={depts} total={stats.inCount} />
          </div>
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
            {todayEntries.map(e => (
              <TodayCard key={e.per_id} entry={e} onFaceClick={openFace} />
            ))}
          </div>
        )}
      </div>

      {/* ── Attendance Table ─────────────────────────────────────────────────── */}
      <div className="table-wrap">
        <div className="table-head">
          <span className="title">รายการลงเวลาวันนี้</span>
          <span className="eb eb-muted">{data.length} records</span>
        </div>
        <AttendanceTable records={data} isLoading={isLoading} />
      </div>

    </div>
    </>
  )
}
