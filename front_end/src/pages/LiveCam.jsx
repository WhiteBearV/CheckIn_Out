import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const STREAM_BASE = import.meta.env.DEV ? 'http://localhost:8001' : ''

// ─── Fetchers ──────────────────────────────────────────────────────────────────

async function fetchCameras() {
  try {
    const r = await fetch(`${STREAM_BASE}/cameras/config`, { signal: AbortSignal.timeout(3000) })
    if (!r.ok) return []
    const data = await r.json()
    return Array.isArray(data) ? data : (data.cameras || [])
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

// state.ts คือ unix timestamp วินาที — ถ้า > 5 วิที่แล้ว ถือว่า offline
function isFresh(state) {
  if (!state || !state.ts) return false
  return (Date.now() / 1000 - state.ts) < 5
}

// ใช้ STREAM_BASE เสมอ (proxy จัดการให้ทั้ง dev และ prod)
async function fetchSystemStatus() {
  try {
    const r = await fetch(`${STREAM_BASE}/system/status`, { signal: AbortSignal.timeout(3000) })
    if (!r.ok) return { face: false, api: false }
    return r.json()
  } catch { return { face: false, api: false } }
}

async function postSystem(action) {
  const r = await fetch(`${STREAM_BASE}/system/${action}`, { method: 'POST' })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

async function postCacheClear() {
  const r = await fetch(`${STREAM_BASE}/cache/clear`, { method: 'POST' })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

// ─── SystemControls — ปุ่ม Start / Stop / Clear Cache (ใหญ่) ─────────────────

function SystemControls() {
  const qc = useQueryClient()
  const [msg, setMsg] = useState('')

  const { data: sys = { face: false, api: false } } = useQuery({
    queryKey:        ['sys-status'],
    queryFn:         fetchSystemStatus,
    refetchInterval: 2000,
  })

  const showMsg = (text, ms = 3000) => {
    setMsg(text)
    setTimeout(() => setMsg(''), ms)
  }

  const startMut = useMutation({
    mutationFn: () => postSystem('start'),
    onSuccess:  (data) => {
      showMsg(`✓ ${JSON.stringify(data)}`)
      setTimeout(() => qc.invalidateQueries({ queryKey: ['sys-status'] }), 1500)
    },
    onError: (e) => showMsg(`✗ ${e.message}`),
  })
  const stopMut = useMutation({
    mutationFn: () => postSystem('stop'),
    onSuccess:  (data) => {
      showMsg(`✓ ${JSON.stringify(data)}`)
      setTimeout(() => qc.invalidateQueries({ queryKey: ['sys-status'] }), 500)
    },
    onError: (e) => showMsg(`✗ ${e.message}`),
  })
  const clearMut = useMutation({
    mutationFn: postCacheClear,
    onSuccess:  () => showMsg('✓ ล้าง cache แล้ว'),
    onError:    (e) => showMsg(`✗ ${e.message}`),
  })

  return (
    <div
      className="rounded p-3 space-y-2"
      style={{ background: 'var(--c-bg-card)', border: '1px solid var(--c-border)' }}
    >
      {/* Status indicators */}
      <div className="flex items-center justify-between font-mono text-[10px] mb-1"
        style={{ color: 'var(--c-text-4)' }}>
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full"
            style={{ background: sys.face ? '#22c55e' : '#ef4444' }} />
          main.py
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full"
            style={{ background: sys.api ? '#22c55e' : '#ef4444' }} />
          api
        </span>
      </div>

      {/* START */}
      <button
        onClick={() => startMut.mutate()}
        disabled={startMut.isPending}
        className="w-full py-3 rounded font-mono font-bold text-base tracking-widest transition-all"
        style={{
          background: startMut.isPending ? '#1a4a1a' : '#22c55e',
          color:      '#000',
          opacity:    startMut.isPending ? 0.7 : 1,
          letterSpacing: '0.2em',
        }}
      >
        {startMut.isPending ? '...' : 'START'}
      </button>

      {/* STOP */}
      <button
        onClick={() => stopMut.mutate()}
        disabled={stopMut.isPending}
        className="w-full py-3 rounded font-mono font-bold text-base tracking-widest transition-all"
        style={{
          background: stopMut.isPending ? '#4a1a1a' : '#dc2626',
          color:      '#fff',
          opacity:    stopMut.isPending ? 0.7 : 1,
          letterSpacing: '0.2em',
        }}
      >
        {stopMut.isPending ? '...' : 'STOP'}
      </button>

      {/* Clear Cache */}
      <button
        onClick={() => clearMut.mutate()}
        disabled={clearMut.isPending}
        className="w-full py-2 rounded font-mono text-[11px] transition-all"
        style={{
          background: 'var(--c-bg-app)',
          color:      'var(--c-text-3)',
          border:     '1px solid var(--c-border)',
        }}
      >
        {clearMut.isPending ? 'กำลังล้าง...' : '🗑 Clear Cache'}
      </button>

      {/* Response message */}
      {msg && (
        <div
          className="font-mono text-[10px] px-2 py-1.5 rounded break-all"
          style={{
            background: msg.startsWith('✓') ? 'rgba(34,197,94,0.10)' : 'rgba(239,68,68,0.10)',
            color:      msg.startsWith('✓') ? '#22c55e' : '#ef4444',
            border:     `1px solid ${msg.startsWith('✓') ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}`,
          }}
        >
          {msg}
        </div>
      )}
    </div>
  )
}

// ─── FullscreenModal ───────────────────────────────────────────────────────────

function FullscreenModal({ cam, onClose }) {
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.92)' }}
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-6xl mx-4"
        style={{ aspectRatio: '16/9' }}
        onClick={e => e.stopPropagation()}
      >
        <img
          src={`${STREAM_BASE}/stream/${cam.id}`}
          alt={cam.name}
          className="w-full h-full object-contain"
        />

        {/* Camera name */}
        <div
          className="absolute top-3 left-3 font-mono text-xs px-2 py-1 rounded"
          style={{ background: 'rgba(0,0,0,0.70)', color: 'rgba(255,255,255,0.80)' }}
        >
          {cam.name || cam.id}
        </div>

        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 w-8 h-8 rounded flex items-center justify-center transition-colors"
          style={{ background: 'rgba(0,0,0,0.70)', color: 'rgba(255,255,255,0.70)' }}
          onMouseEnter={e => e.currentTarget.style.background = 'rgba(239,68,68,0.70)'}
          onMouseLeave={e => e.currentTarget.style.background = 'rgba(0,0,0,0.70)'}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {/* ESC hint */}
        <div
          className="absolute bottom-3 right-3 font-mono text-[10px] px-2 py-1 rounded"
          style={{ background: 'rgba(0,0,0,0.60)', color: 'rgba(255,255,255,0.30)' }}
        >
          ESC to close
        </div>
      </div>
    </div>
  )
}

// ─── CameraCell ────────────────────────────────────────────────────────────────

function CameraCell({ cam, isOnline, onExpand }) {
  const borderColor = isOnline ? 'rgba(34,197,94,0.35)' : 'rgba(239,68,68,0.40)'

  return (
    <div
      className="relative rounded overflow-hidden group"
      style={{
        background:  'var(--c-bg-deep)',
        border:      `1px solid ${borderColor}`,
        aspectRatio: '16/9',
        transition:  'border-color 0.3s',
      }}
    >
      {/* MJPEG stream — backend วาด overlay ให้ครบแล้ว */}
      <img
        src={`${STREAM_BASE}/stream/${cam.id}`}
        alt={cam.name}
        className="w-full h-full object-contain"
      />

      {/* Status badge — มุมซ้ายบน */}
      <div
        className="absolute top-2 left-2 flex items-center gap-1.5 px-2 py-1 rounded"
        style={{ background: 'rgba(0,0,0,0.72)', border: `1px solid ${borderColor}` }}
      >
        <span className="relative flex w-1.5 h-1.5">
          {isOnline && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#22c55e] opacity-60" />
          )}
          <span
            className="relative inline-flex rounded-full w-1.5 h-1.5"
            style={{ background: isOnline ? '#22c55e' : '#ef4444' }}
          />
        </span>
        <span
          className="font-mono text-[10px]"
          style={{ color: isOnline ? 'rgba(255,255,255,0.80)' : '#ef4444' }}
        >
          {isOnline ? (cam.name || cam.id) : 'OFFLINE'}
        </span>
      </div>

      {/* Offline center label */}
      {!isOnline && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <span
            className="font-mono text-xs uppercase tracking-widest"
            style={{ color: 'rgba(239,68,68,0.35)' }}
          >
            Camera Offline
          </span>
        </div>
      )}

      {/* Expand button — มุมขวาบน แสดงเมื่อ hover */}
      <button
        onClick={() => onExpand(cam)}
        className="absolute top-2 right-2 w-7 h-7 rounded flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: 'rgba(0,0,0,0.70)', color: 'rgba(255,255,255,0.80)' }}
        title="ดูเต็มจอ"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
        </svg>
      </button>
    </div>
  )
}

// ─── helpers ──────────────────────────────────────────────────────────────────

const SCAN_TIMEOUT_SEC = 10

/** แปลง "HH:MM:SS" → Date วันนี้ */
function parseTimeStr(str) {
  if (!str || str === '-') return null
  const parts = str.split(':').map(Number)
  if (parts.length < 3 || parts.some(isNaN)) return null
  const d = new Date()
  d.setHours(parts[0], parts[1], parts[2], 0)
  return d
}

/** คำนวณวินาทีที่ผ่านไปตั้งแต่ first_seen */
function elapsedSec(firstSeenStr) {
  const t = parseTimeStr(firstSeenStr)
  if (!t) return 0
  return (Date.now() - t.getTime()) / 1000
}

// ─── PersonPanelCard ───────────────────────────────────────────────────────────

function PersonPanelCard({ camId, camName, name, person, cacheBust }) {
  const elapsed = elapsedSec(person.first_seen)
  const st = person.checked_out
    ? { label: 'ออกงาน',         color: '#f97316' }
    : person.checked_in
    ? { label: 'เข้างาน',        color: '#22c55e' }
    : elapsed > SCAN_TIMEOUT_SEC
    ? { label: 'สแกนไม่สำเร็จ',  color: '#ef4444' }
    : { label: 'กำลังสแกน',      color: '#eab308' }

  return (
    <div
      className="flex gap-2.5 p-2.5 rounded"
      style={{
        background: 'var(--c-bg-app)',
        border:     '1px solid var(--c-border-s)',
        borderLeft: `2px solid ${st.color}`,
      }}
    >
      {/* Face thumbnail — cache-bust ทุกครั้ง */}
      <div
        className="w-10 h-10 flex-shrink-0 rounded overflow-hidden"
        style={{ background: 'var(--c-bg-deep)', border: '1px solid var(--c-border-s)' }}
      >
        <img
          src={`${STREAM_BASE}/snap/${camId}/${encodeURIComponent(name)}?t=${cacheBust}`}
          alt=""
          className="w-full h-full object-cover"
          onError={e => { e.currentTarget.style.display = 'none' }}
        />
      </div>

      <div className="flex-1 min-w-0">
        <div className="font-mono text-[11px] truncate leading-tight"
          style={{ color: 'var(--c-accent)' }}>
          {person.display_name || name}
        </div>
        {/* ชื่อกล้องที่ตรวจพบ */}
        <div className="font-mono text-[9px] truncate"
          style={{ color: 'var(--c-text-4)' }}>
          📷 {camName || camId}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="font-mono text-[10px]" style={{ color: st.color }}>
            • {st.label}
          </span>
          {person.first_seen && person.first_seen !== '-' && (
            <span className="font-mono text-[10px]" style={{ color: 'var(--c-text-4)' }}>
              {person.first_seen}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Main ──────────────────────────────────────────────────────────────────────

export default function LiveCam() {
  const [allStates,     setAllStates]     = useState({})
  const [fullscreenCam, setFullscreenCam] = useState(null)
  const [cacheBust,     setCacheBust]     = useState(0)
  const pollRef = useRef(null)

  // cacheBust ทุก 3 วิ → บังคับรูปโหลดใหม่
  useEffect(() => {
    const t = setInterval(() => setCacheBust(Date.now()), 3000)
    return () => clearInterval(t)
  }, [])

  // Camera list
  const { data: cameras = [] } = useQuery({
    queryKey: ['cameras-config'],
    queryFn:  fetchCameras,
    refetchInterval: 5000,
  })

  // Poll camera states ทุก 1 วิ
  const pollStates = useCallback(async () => {
    if (!cameras.length) {
      pollRef.current = setTimeout(pollStates, 500)
      return
    }
    const results = await Promise.allSettled(cameras.map(c => fetchCamState(c.id)))
    setAllStates(prev => {
      const next = { ...prev }
      cameras.forEach((c, i) => {
        const res = results[i]
        if (res.status === 'fulfilled' && res.value && isFresh(res.value))
          next[c.id] = res.value
        else
          delete next[c.id]   // offline หรือ state เก่า → ถือว่า offline
      })
      return next
    })
    pollRef.current = setTimeout(pollStates, 1000)
  }, [cameras])

  useEffect(() => {
    pollStates()
    return () => clearTimeout(pollRef.current)
  }, [pollStates])

  // Aggregate persons จากทุกกล้อง รวม camName
  const allPersons = useMemo(() => {
    const list = []
    cameras.forEach(c => {
      const persons = allStates[c.id]?.persons
      if (persons)
        Object.entries(persons).forEach(([name, p]) =>
          list.push({ camId: c.id, camName: c.name || c.id, name, person: p })
        )
    })
    return list
  }, [allStates, cameras])

  const activeCamCount = cameras.filter(c => !!allStates[c.id]).length
  const gridCols = cameras.length <= 1 ? 'grid-cols-1' : 'grid-cols-2'

  return (
    <>
      {/* ── Fullscreen Modal ──────────────────────────────────────────────────── */}
      {fullscreenCam && (
        <FullscreenModal cam={fullscreenCam} onClose={() => setFullscreenCam(null)} />
      )}

      <div className="p-5 space-y-4 overflow-auto" style={{ minHeight: '100%' }}>

        {/* ── Header ───────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full animate-pulse"
              style={{ background: 'var(--c-accent)' }} />
            <h1 className="text-lg font-light tracking-tight" style={{ color: 'var(--c-text)' }}>
              Face Recognition
            </h1>
            <span
              className="font-mono text-[10px] px-2 py-0.5 rounded"
              style={{
                background: 'var(--c-accent-bg)',
                color:      'var(--c-accent)',
                border:     '1px solid var(--c-accent-border)',
              }}
            >
              {cameras.length} cam{cameras.length !== 1 ? 's' : ''}
            </span>
            <span
              className="font-mono text-[10px] px-2 py-0.5 rounded uppercase tracking-widest"
              style={{
                background: 'rgba(239,68,68,0.08)',
                color:      '#ef4444',
                border:     '1px solid rgba(239,68,68,0.22)',
              }}
            >
              LIVE
            </span>
          </div>
        </div>

        {/* ── Camera Grid + Right Panel ─────────────────────────────────────────── */}
        <div className="flex gap-3">

          {/* Camera Grid */}
          <div className={`flex-1 grid ${gridCols} gap-2 content-start`}>
            {cameras.length === 0 ? (
              <div
                className="rounded flex items-center justify-center col-span-2"
                style={{
                  background:  'var(--c-bg-card)',
                  border:      '1px solid var(--c-border)',
                  aspectRatio: '16/9',
                }}
              >
                <div className="text-center">
                  <p className="font-mono text-[11px] uppercase tracking-widest mb-1"
                    style={{ color: 'var(--c-text-4)' }}>ไม่พบกล้อง</p>
                  <p className="font-mono text-[10px]" style={{ color: 'var(--c-text-4)' }}>
                    ตรวจสอบ cameras.json
                  </p>
                </div>
              </div>
            ) : cameras.map(cam => (
              <CameraCell
                key={cam.id}
                cam={cam}
                isOnline={!!allStates[cam.id]}
                onExpand={setFullscreenCam}
              />
            ))}
          </div>

          {/* Right Panel */}
          <div className="w-60 flex-shrink-0 flex flex-col gap-2">

            {/* Live persons header */}
            <div
              className="px-3 py-2 rounded"
              style={{ background: 'var(--c-bg-card)', border: '1px solid var(--c-border)' }}
            >
              <div className="flex items-center gap-2 flex-wrap text-[10px] font-mono">
                <span className="flex items-center gap-1" style={{ color: '#22c55e' }}>
                  <span className="relative flex w-1.5 h-1.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#22c55e] opacity-60" />
                    <span className="relative inline-flex rounded-full w-1.5 h-1.5 bg-[#22c55e]" />
                  </span>
                  LIVE
                </span>
                <span style={{ color: 'var(--c-text-3)' }}>ตรวจพบ</span>
                <span style={{ color: 'var(--c-accent)' }}>{allPersons.length} คน</span>
                <span className="ml-auto" style={{ color: 'var(--c-text-4)' }}>
                  • กำลังทำงาน {activeCamCount}x
                </span>
              </div>
            </div>

            {/* Person cards */}
            <div className="space-y-1.5 overflow-y-auto" style={{ maxHeight: 200 }}>
              {allPersons.length === 0 ? (
                <div
                  className="py-4 text-center font-mono text-[10px]"
                  style={{ color: 'var(--c-text-4)' }}
                >
                  ไม่พบใบหน้า
                </div>
              ) : allPersons.map(({ camId, camName, name, person }) => (
                <PersonPanelCard
                  key={`${camId}-${name}`}
                  camId={camId} camName={camName}
                  name={name} person={person}
                  cacheBust={cacheBust}
                />
              ))}
            </div>

            {/* System status */}
            <div
              className="rounded p-2.5"
              style={{ background: 'var(--c-bg-card)', border: '1px solid var(--c-border)' }}
            >
              <p
                className="font-mono text-[10px] uppercase tracking-widest mb-2"
                style={{ color: 'var(--c-text-4)' }}
              >
                สถานะระบบ
              </p>
              <div className="space-y-1.5">
                {cameras.map(cam => {
                  const state  = allStates[cam.id]
                  const online = !!state
                  return (
                    <div key={cam.id}>
                      <div className="flex items-center gap-2">
                        <span className="relative flex w-1.5 h-1.5 flex-shrink-0">
                          {online && (
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#22c55e] opacity-50" />
                          )}
                          <span
                            className="relative inline-flex rounded-full w-1.5 h-1.5"
                            style={{ background: online ? '#22c55e' : '#ef4444' }}
                          />
                        </span>
                        <span
                          className="font-mono text-[10px] flex-1 truncate"
                          style={{ color: 'var(--c-text-2)' }}
                        >
                          {cam.name}
                        </span>
                        <span
                          className="font-mono text-[9px]"
                          style={{ color: online ? '#22c55e' : '#ef4444' }}
                        >
                          {online ? `${(state.fps || 0).toFixed(0)} fps` : 'offline'}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Tips */}
            <div
              className="rounded p-2.5"
              style={{ background: 'var(--c-bg-card)', border: '1px solid var(--c-border)' }}
            >
              <p
                className="font-mono text-[10px] uppercase tracking-widest mb-2"
                style={{ color: 'var(--c-text-4)' }}
              >
                วิธีใช้ (OpenCV)
              </p>
              {[['R','รีโหลดกล้อง'],['+','เพิ่มกล้อง'],['×','ลบกล้อง'],['F','เต็มจอ'],['Q','ออก']].map(([k, v]) => (
                <div key={k} className="flex items-center gap-2 mb-1">
                  <span
                    className="font-mono text-[9px] px-1.5 py-0.5 rounded text-center"
                    style={{
                      background: 'var(--c-bg-app)',
                      color:      'var(--c-text-2)',
                      border:     '1px solid var(--c-border)',
                      minWidth:   20,
                    }}
                  >
                    {k}
                  </span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--c-text-3)' }}>
                    {v}
                  </span>
                </div>
              ))}
            </div>

            {/* START / STOP / Clear Cache */}
            <SystemControls />

          </div>
        </div>

      </div>
    </>
  )
}
