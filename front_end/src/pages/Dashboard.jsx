import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, useEffect, useCallback, useRef } from 'react'
import StatCard from '../components/StatCard'
import AttendanceTable from '../components/AttendanceTable'
import { fetchAttendanceToday } from '../api/attendance'

const REFRESH_INTERVAL  = 30_000
const SCAN_TIMEOUT_SEC  = 10
const STREAM_BASE = import.meta.env.DEV ? 'http://localhost:8001' : ''

// ─── Mock data (เปิด/ปิดด้วย USE_MOCK) ────────────────────────────────────────
const USE_MOCK = true   // TODO: ลบ mock ออกก่อน deploy — เปลี่ยนเป็น false เพื่อใช้ API จริง

const MOCK_RECORDS = [
  { id:1,  per_id:'EMP001', per_name:'สุชาติ',    per_surname:'อินทรประสิทธิ์', organize_th:'สำนักวิจัย',          status:'IN',  check_time:'2026-04-20T08:12:40', cam_id:'cam_main' },
  { id:2,  per_id:'EMP002', per_name:'ปรียา',      per_surname:'วัฒนกุล',        organize_th:'คณะครุศาสตร์',        status:'IN',  check_time:'2026-04-20T08:14:22', cam_id:'cam_main' },
  { id:3,  per_id:'EMP003', per_name:'วราวุธ',     per_surname:'โสภิต',           organize_th:'กองกลาง',             status:'IN',  check_time:'2026-04-20T08:55:08', cam_id:'cam_web'  },
  { id:4,  per_id:'EMP004', per_name:'นันทวัน',    per_surname:'ศรีรัตน์',        organize_th:'สำนักวิจัย',          status:'IN',  check_time:'2026-04-20T09:02:13', cam_id:'cam_main' },
  { id:5,  per_id:'EMP005', per_name:'ปิยะดา',     per_surname:'เจริญสุข',        organize_th:'กองการเงิน',          status:'OUT', check_time:'2026-04-20T12:15:49', cam_id:'cam_web'  },
  { id:6,  per_id:'EMP006', per_name:'ธนกร',       per_surname:'เกียรติศักดิ์',   organize_th:'กองสื่อสารองค์กร',   status:'OUT', check_time:'2026-04-20T12:20:06', cam_id:'cam_main' },
  { id:7,  per_id:'EMP007', per_name:'วิภาวี',     per_surname:'ชินวัตร',         organize_th:'คณะวิศวกรรมศาสตร์',  status:'IN',  check_time:'2026-04-20T13:02:18', cam_id:'cam_web'  },
  { id:8,  per_id:'EMP008', per_name:'ธีรพล',      per_surname:'มงคลสวัสดิ์',    organize_th:'คณะวิศวกรรมศาสตร์',  status:'IN',  check_time:'2026-04-20T07:58:01', cam_id:'cam_main' },
  { id:9,  per_id:'EMP009', per_name:'สมหญิง',     per_surname:'รักษาวงศ์',       organize_th:'คณะครุศาสตร์',        status:'IN',  check_time:'2026-04-20T08:30:55', cam_id:'cam_web'  },
  { id:10, per_id:'EMP010', per_name:'ประเสริฐ',   per_surname:'ทองดี',           organize_th:'กองกลาง',             status:'IN',  check_time:'2026-04-20T08:45:12', cam_id:'cam_main' },
  { id:11, per_id:'EMP011', per_name:'มาลี',       per_surname:'สุขใจ',           organize_th:'กองการเงิน',          status:'IN',  check_time:'2026-04-20T09:10:44', cam_id:'cam_web'  },
  { id:12, per_id:'EMP012', per_name:'อนุชา',      per_surname:'พรหมมา',          organize_th:'สำนักวิจัย',          status:'OUT', check_time:'2026-04-20T11:50:33', cam_id:'cam_main' },
  { id:13, per_id:'EMP013', per_name:'กนกวรรณ',    per_surname:'เพ็ญศรี',         organize_th:'คณะวิศวกรรมศาสตร์',  status:'IN',  check_time:'2026-04-20T08:05:27', cam_id:'cam_web'  },
  { id:14, per_id:'EMP014', per_name:'จิรายุ',     per_surname:'แก้วมณี',         organize_th:'กองสื่อสารองค์กร',   status:'IN',  check_time:'2026-04-20T08:22:18', cam_id:'cam_main' },
  { id:15, per_id:'EMP015', per_name:'รัตนา',      per_surname:'สมบูรณ์',         organize_th:'สำนักวิจัย',          status:'IN',  check_time:'2026-04-20T08:03:55', cam_id:'cam_main' },
  { id:16, per_id:'EMP016', per_name:'พิชัย',      per_surname:'ลาภมาก',          organize_th:'คณะครุศาสตร์',        status:'OUT', check_time:'2026-04-20T13:45:00', cam_id:'cam_web'  },
  { id:17, per_id:'EMP017', per_name:'สายชล',      per_surname:'บุญเรือง',        organize_th:'กองกลาง',             status:'IN',  check_time:'2026-04-20T09:20:10', cam_id:'cam_main' },
  { id:18, per_id:'EMP018', per_name:'ณัฐพล',      per_surname:'วงษ์สุวรรณ',     organize_th:'คณะวิศวกรรมศาสตร์',  status:'IN',  check_time:'2026-04-20T07:50:33', cam_id:'cam_web'  },
  { id:19, per_id:'EMP019', per_name:'ชลธิชา',     per_surname:'จันทร์เพ็ญ',     organize_th:'กองการเงิน',          status:'IN',  check_time:'2026-04-20T08:38:47', cam_id:'cam_main' },
  { id:20, per_id:'EMP020', per_name:'สมศักดิ์',   per_surname:'เดชขุน',          organize_th:'สำนักวิจัย',          status:'OUT', check_time:'2026-04-20T12:05:19', cam_id:'cam_web'  },
  { id:21, per_id:'EMP021', per_name:'พรทิพย์',    per_surname:'นาคสุข',          organize_th:'คณะครุศาสตร์',        status:'IN',  check_time:'2026-04-20T08:48:26', cam_id:'cam_main' },
  { id:22, per_id:'EMP022', per_name:'วิชาญ',      per_surname:'มีสุข',           organize_th:'กองสื่อสารองค์กร',   status:'IN',  check_time:'2026-04-20T09:05:52', cam_id:'cam_web'  },
  { id:23, per_id:'EMP023', per_name:'อรอุมา',     per_surname:'ฤทธิ์ดี',         organize_th:'คณะวิศวกรรมศาสตร์',  status:'OUT', check_time:'2026-04-20T11:30:07', cam_id:'cam_main' },
  { id:24, per_id:'EMP024', per_name:'ศุภชัย',     per_surname:'โกมลวิทย์',      organize_th:'สำนักวิจัย',          status:'IN',  check_time:'2026-04-20T08:17:39', cam_id:'cam_web'  },
  { id:25, per_id:'EMP025', per_name:'กาญจนา',     per_surname:'ดีสม',            organize_th:'กองกลาง',             status:'IN',  check_time:'2026-04-20T08:59:11', cam_id:'cam_main' },
  { id:26, per_id:'EMP026', per_name:'ทวีศักดิ์',  per_surname:'สุขสบาย',        organize_th:'คณะครุศาสตร์',        status:'IN',  check_time:'2026-04-20T07:45:03', cam_id:'cam_web'  },
  { id:27, per_id:'EMP027', per_name:'นิภา',       per_surname:'แสงทอง',          organize_th:'กองการเงิน',          status:'OUT', check_time:'2026-04-20T13:10:28', cam_id:'cam_main' },
  { id:28, per_id:'EMP028', per_name:'ภาณุวัฒน์',  per_surname:'ชูชีพ',           organize_th:'คณะวิศวกรรมศาสตร์',  status:'IN',  check_time:'2026-04-20T08:28:44', cam_id:'cam_web'  },
  { id:29, per_id:'EMP029', per_name:'สุนีย์',     per_surname:'พูลสวัสดิ์',      organize_th:'กองสื่อสารองค์กร',   status:'IN',  check_time:'2026-04-20T09:33:16', cam_id:'cam_main' },
  { id:30, per_id:'EMP030', per_name:'ไพโรจน์',    per_surname:'ศรีสวัสดิ์',      organize_th:'สำนักวิจัย',          status:'IN',  check_time:'2026-04-20T08:08:59', cam_id:'cam_web'  },
]

const MOCK_HOURLY = [0,0,0,0,0,0,0,3,28,42,8,4,12,15,2,1,2,8,4,1,0,0,0,0]

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
  const endpoint = isSquare ? 'snapfull' : 'snap'  // square = full frame, circle = face crop
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
        style={{
          width: '100%', height: 79,
          overflow: 'hidden', position: 'relative',
          background: 'var(--c-bg-deep)',
          borderRadius: '6px 6px 0 0',
        }}
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
    queryFn:         USE_MOCK ? () => MOCK_RECORDS : fetchAttendanceToday,
    refetchInterval: USE_MOCK ? false : REFRESH_INTERVAL,
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
    <div className="page">

      {/* ── Mock warning banner ─────────────────────────────────────────────── */}
      {USE_MOCK && (
        <div style={{
          background: 'rgba(234,179,8,0.10)', border: '1px solid rgba(234,179,8,0.35)',
          borderRadius: 'var(--radius-sm)', padding: '8px 14px',
          fontFamily: 'var(--font-mono)', fontSize: 11, color: '#eab308',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          ⚠ MOCK MODE — ข้อมูลจำลอง ไม่ใช่ข้อมูลจริง · ลบออกก่อน deploy (Dashboard.jsx บรรทัด 12)
        </div>
      )}

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
            {data.map(r => (
              <TodayCard key={r.id} record={r} activeCams={activeCams} onFaceClick={openFace} />
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
