import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchPerson } from '../api/attendance'
import { authFetch } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { maskPid } from '../utils/pid'

const STREAM_BASE = import.meta.env.DEV ? 'http://localhost:8001' : ''

// ─── Fetchers ──────────────────────────────────────────────────────────────────

async function fetchCameras() {
  try {
    const r = await authFetch(`${STREAM_BASE}/cameras/config`, { signal: AbortSignal.timeout(3000) })
    if (!r.ok) return []
    const data = await r.json()
    return Array.isArray(data) ? data : (data.cameras || [])
  } catch { return [] }
}

async function fetchCamState(camId) {
  try {
    const r = await authFetch(`${STREAM_BASE}/state/${camId}`, {
      cache: 'no-store', signal: AbortSignal.timeout(1500),
    })
    if (!r.ok) return null
    return r.json()
  } catch { return null }
}

// state.ts คือ unix timestamp วินาที — ถ้า > 8 วิที่แล้ว ถือว่า offline
function isFresh(state) {
  if (!state || !state.ts) return false
  return (Date.now() / 1000 - state.ts) < 8
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
  const r = await authFetch(`${STREAM_BASE}/system/${action}`, { method: 'POST' })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

async function postCacheClear() {
  const r = await authFetch(`${STREAM_BASE}/cache/clear`, { method: 'POST' })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

async function postCamerasReload() {
  const r = await authFetch(`${STREAM_BASE}/cameras/reload`, { method: 'POST' })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

async function postAddCamera(body) {
  const r = await authFetch(`${STREAM_BASE}/cameras/config`, {
    method: 'POST',
    body,
  })
  if (!r.ok) {
    // 409 = ซ้ำ, 400 = invalid input — backend ส่ง error message ภาษาไทยเป็น text
    const msg = await r.text().catch(() => '')
    const err = new Error(msg || `HTTP ${r.status}`)
    err.status = r.status
    throw err
  }
  return r.json()
}

async function deleteCamera(camId) {
  const r = await authFetch(`${STREAM_BASE}/cameras/config/${encodeURIComponent(camId)}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

// ─── CamStream — snapshot polling แทน MJPEG stream ───────────────────────────
// fetch /snapshot ทุก 120ms (~8fps) — ไม่มีปัญหา long-lived connection hang
const SNAP_INTERVAL = 120

function CamStream({ camId, style, className }) {
  const [src, setSrc]    = useState('')
  const aliveRef         = useRef(true)
  const prevUrlRef       = useRef('')

  useEffect(() => {
    aliveRef.current = true
    setSrc('')
    if (prevUrlRef.current) { URL.revokeObjectURL(prevUrlRef.current); prevUrlRef.current = '' }

    ;(async () => {
      while (aliveRef.current) {
        try {
          const r = await authFetch(
            `${STREAM_BASE}/snapshot/${camId}?_=${Date.now()}`,
            { signal: AbortSignal.timeout(1200), cache: 'no-store' }
          )
          if (r.ok && aliveRef.current) {
            const blob = await r.blob()
            const url  = URL.createObjectURL(blob)
            setSrc(url)
            if (prevUrlRef.current) URL.revokeObjectURL(prevUrlRef.current)
            prevUrlRef.current = url
          }
        } catch {}
        if (aliveRef.current) await new Promise(res => setTimeout(res, SNAP_INTERVAL))
      }
      if (prevUrlRef.current) URL.revokeObjectURL(prevUrlRef.current)
    })()

    return () => { aliveRef.current = false }
  }, [camId])

  if (!src) return null
  return <img src={src} alt="" style={style} className={className} draggable={false} />
}

// ─── BtnSpinner ────────────────────────────────────────────────────────────────

function BtnSpinner() {
  return (
    <svg style={{ animation: 'spin 0.75s linear infinite' }} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
      <path d="M12 2a10 10 0 0 1 0 20A10 10 0 0 1 2 12" />
    </svg>
  )
}

// ─── SystemControls — ปุ่ม Start / Stop / Clear Cache ────────────────────────

function SystemControls({ onStart, onClearDone, cameras = [] }) {
  const qc = useQueryClient()
  const { isAdmin } = useAuth()
  const [cacheMsg, setCacheMsg] = useState('')

  const { data: sys = { face: false, api: false } } = useQuery({
    queryKey:        ['sys-status'],
    queryFn:         fetchSystemStatus,
    refetchInterval: 2000,
  })

  const showCache = (text, ms = 3000) => {
    setCacheMsg(text)
    setTimeout(() => setCacheMsg(''), ms)
  }

  const startMut = useMutation({
    mutationFn: () => postSystem('start'),
    onSuccess:  () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ['sys-status'] }), 1500)
      onStart?.(cameras)   // ส่ง cameras list เพื่อ set connecting state
    },
    onError:    (e) => showCache(`✗ ${e.message}`),
  })
  const stopMut = useMutation({
    mutationFn: () => postSystem('stop'),
    onSuccess:  () => setTimeout(() => qc.invalidateQueries({ queryKey: ['sys-status'] }), 500),
    onError:    (e) => showCache(`✗ ${e.message}`),
  })
  const clearMut = useMutation({
    mutationFn: postCacheClear,
    onSuccess:  () => {
      showCache('✓ ล้าง cache แล้ว')
      qc.invalidateQueries()
      onClearDone?.()
    },
    onError: (e) => showCache(`✗ ${e.message}`),
  })

  return (
    <div className="panel">
      <div className="p-head">
        <span className="eb">SYSTEM</span>
        <span className="eb eb-muted">main.py</span>
      </div>
      <div className="p-body" style={{ display: 'grid', gap: 8 }}>
        {/* Status indicators */}
        <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-4)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: sys.face ? '#22c55e' : '#ef4444', display: 'inline-block' }} />
            main.py
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: sys.api ? '#22c55e' : '#ef4444', display: 'inline-block' }} />
            api
          </span>
        </div>

        {/* START / STOP toggle */}
        {sys.face
          ? <button onClick={() => stopMut.mutate()} disabled={stopMut.isPending || !isAdmin}
              className="btn btn-stop btn-block"
              title={isAdmin ? '' : 'admin เท่านั้นที่สั่ง STOP ได้'}>
              {stopMut.isPending
                ? <><BtnSpinner /> กำลังหยุด...</>
                : <><svg fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><rect x="5" y="5" width="14" height="14" rx="1"/></svg>STOP</>
              }
            </button>
          : <button onClick={() => startMut.mutate()} disabled={startMut.isPending || !isAdmin}
              className="btn btn-start btn-block"
              title={isAdmin ? '' : 'admin เท่านั้นที่สั่ง START ได้'}>
              {startMut.isPending
                ? <><BtnSpinner /> กำลังเริ่ม...</>
                : <><svg fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M5 3l14 9-14 9V3z"/></svg>START</>
              }
            </button>
        }

        {/* Clear Cache — ใช้ได้เฉพาะตอน Stop */}
        <button onClick={() => clearMut.mutate()} disabled={sys.face || clearMut.isPending || !isAdmin}
          className="btn btn-ghost btn-block btn-sm"
          title={!isAdmin ? 'admin เท่านั้น' : (sys.face ? 'หยุดระบบก่อนล้าง cache' : 'ล้าง snapshot cache')}>
          {clearMut.isPending
            ? <><BtnSpinner /> กำลังล้าง...</>
            : <><svg fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>Clear Cache</>
          }
        </button>

        {cacheMsg && (
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, padding: '6px 8px', borderRadius: 4,
            background: cacheMsg.startsWith('✓') ? 'rgba(34,197,94,0.10)' : 'rgba(239,68,68,0.10)',
            color:      cacheMsg.startsWith('✓') ? '#22c55e' : '#ef4444',
            border:     `1px solid ${cacheMsg.startsWith('✓') ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}`,
          }}>
            {cacheMsg}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── FaceModal — ขยายรูปหน้าให้ดูได้ชัด ──────────────────────────────────────

function FaceModal({ src, name, onClose }) {
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 10000,
        background: 'rgba(0,0,0,0.90)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}
        onClick={e => e.stopPropagation()}>
        <img src={src} alt={name}
          style={{ maxWidth: '80vw', maxHeight: '70vh', borderRadius: 6, border: '1px solid rgba(255,255,255,0.12)', objectFit: 'contain' }} />
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>{name}</p>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'rgba(255,255,255,0.25)' }}>ESC หรือคลิกพื้นหลังเพื่อปิด</p>
        <button onClick={onClose} style={{
          position: 'absolute', top: -10, right: -10, width: 28, height: 28, borderRadius: '50%',
          background: 'rgba(239,68,68,0.85)', border: 'none', color: '#fff', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg style={{ width: 14, height: 14 }} fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  )
}

// ─── FullscreenModal — ใช้ Browser Fullscreen API ─────────────────────────────

function FullscreenModal({ cam, onClose }) {
  const modalRef = useRef(null)

  // เข้า fullscreen ทันทีที่ modal เปิด
  useEffect(() => {
    const el = modalRef.current
    if (!el) return
    el.requestFullscreen?.().catch(() => {})
    return () => {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
    }
  }, [])

  // ออก modal เมื่อ browser ออกจาก fullscreen (ปุ่ม ESC ของ browser)
  useEffect(() => {
    const onFsChange = () => { if (!document.fullscreenElement) onClose() }
    document.addEventListener('fullscreenchange', onFsChange)
    return () => document.removeEventListener('fullscreenchange', onFsChange)
  }, [onClose])

  const handleClose = useCallback(() => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
    else onClose()
  }, [onClose])

  return (
    <div
      ref={modalRef}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: '#000',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={handleClose}
    >
      <div onClick={e => e.stopPropagation()} style={{ maxWidth: '100%', maxHeight: '100%' }}>
        <CamStream
          camId={cam.id}
          style={{ maxWidth: '100vw', maxHeight: '100vh', objectFit: 'contain', display: 'block' }}
        />
      </div>

      {/* Camera name pill */}
      <div
        style={{
          position: 'absolute', top: 16, left: 16,
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '5px 12px',
          background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(6px)',
          border: '1px solid rgba(255,255,255,0.10)',
          borderRadius: 4,
          fontFamily: 'var(--font-mono)', fontSize: 12,
          color: 'rgba(255,255,255,0.85)',
          pointerEvents: 'none',
        }}
        onClick={e => e.stopPropagation()}
      >
        <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#ef4444', animation: 'blink 1s infinite', display: 'inline-block' }} />
        {cam.name || cam.id}
      </div>

      {/* Close button */}
      <button
        onClick={handleClose}
        style={{
          position: 'absolute', top: 16, right: 16,
          width: 36, height: 36, borderRadius: 4, border: '1px solid rgba(255,255,255,0.15)',
          background: 'rgba(0,0,0,0.75)', color: 'rgba(255,255,255,0.7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', backdropFilter: 'blur(6px)',
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'rgba(239,68,68,0.75)'}
        onMouseLeave={e => e.currentTarget.style.background = 'rgba(0,0,0,0.75)'}
      >
        <svg style={{ width: 16, height: 16 }} fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      <div style={{
        position: 'absolute', bottom: 16, right: 16,
        fontFamily: 'var(--font-mono)', fontSize: 10, padding: '3px 8px',
        background: 'rgba(0,0,0,0.6)', color: 'rgba(255,255,255,0.3)',
        borderRadius: 3, pointerEvents: 'none',
      }}>
        ESC to exit fullscreen
      </div>
    </div>
  )
}

// ─── CameraCell ────────────────────────────────────────────────────────────────

function CameraCell({ cam, isOnline, isIdle, isConnecting, onExpand, onSelect }) {
  const camAccent = isOnline
    ? (isIdle ? '#6366f1' : '#22c55e')
    : isConnecting ? '#eab308' : '#ef4444'

  return (
    <div
      className="cam"
      style={{ '--cam-accent': camAccent, cursor: onSelect ? 'pointer' : 'default' }}
      onClick={() => onSelect?.(cam)}
    >
      {isOnline ? (
        <>
          {/* CamStream — snapshot polling ทุก 120ms ไม่มีปัญหา MJPEG connection */}
          <CamStream
            camId={cam.id}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain' }}
          />
          <div
            className="badge"
            style={isIdle ? { background: 'rgba(99,102,241,0.85)' } : undefined}
          >
            {isIdle ? 'IDLE' : 'LIVE'}
          </div>
        </>
      ) : isConnecting ? (
        <>
          {/* Connecting state — กำลังพยายามเชื่อมต่อ */}
          <div className="badge" style={{ background: 'rgba(234,179,8,0.85)', color: '#000' }}>CONNECTING</div>
          <div style={{
            position: 'absolute', inset: 0,
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            gap: 10, pointerEvents: 'none',
          }}>
            <svg style={{ width: 22, height: 22, animation: 'spin 0.9s linear infinite', stroke: 'rgba(234,179,8,0.7)', fill: 'none', strokeWidth: 2 }} viewBox="0 0 24 24">
              <path d="M12 2a10 10 0 0 1 0 20A10 10 0 0 1 2 12" strokeLinecap="round"/>
            </svg>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(234,179,8,0.6)', textAlign: 'center', padding: '0 8px' }}>
              Try connect<br/>please wait
            </span>
          </div>
        </>
      ) : (
        <>
          <div className="badge" style={{ background: 'rgba(239,68,68,0.85)' }}>OFFLINE</div>
          <div style={{
            position: 'absolute', inset: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            pointerEvents: 'none',
          }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'rgba(239,68,68,0.35)' }}>
              Camera Offline
            </span>
          </div>
        </>
      )}

      <div className="label"><span>{cam.name || cam.id}</span></div>

      {onSelect && (
        <div className="cam-focus-hint">
          <svg style={{ width: 22, height: 22 }} fill="none" stroke="white" strokeWidth="1.5" viewBox="0 0 24 24">
            <rect x="3" y="3" width="8" height="13" rx="1"/>
            <rect x="13" y="3" width="8" height="5" rx="1"/>
            <rect x="13" y="11" width="8" height="5" rx="1"/>
          </svg>
        </div>
      )}

      <button
        className="expand-btn"
        style={onSelect ? { opacity: 1 } : undefined}
        onClick={e => { e.stopPropagation(); onExpand(cam) }}
        title="ดูเต็มจอ"
      >
        <svg fill="none" stroke="white" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 20.25h-4.5m4.5 0v-4.5m0 4.5L15 15"/>
        </svg>
      </button>
    </div>
  )
}

// ─── CameraManager ────────────────────────────────────────────────────────────

function CameraManager({ cameras, onReload }) {
  const qc = useQueryClient()
  const { isAdmin } = useAuth()
  const [open, setOpen]     = useState(false)
  const [msg,  setMsg]      = useState('')
  const [form, setForm]     = useState({ name: '', cam_type: 'usb', url: '', index: '0', flip: false })

  const showMsg = (text, ms = 3000) => { setMsg(text); setTimeout(() => setMsg(''), ms) }
  const showErr = (text) => showMsg(`✗ ${text}`, 6000)   // error แสดงนานกว่า — ผู้ใช้ต้องอ่าน

  const reloadMut = useMutation({
    mutationFn: postCamerasReload,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['cameras-config'] })
      onReload?.()
      showMsg(data?.msg ? `✓ ${data.msg}` : '✓ Hotload สำเร็จ')
    },
    onError: () => showMsg('✗ Reload ไม่สำเร็จ — ลอง Start/Stop ระบบ'),
  })

  const addMut = useMutation({
    mutationFn: () => postAddCamera({
      name:     form.name,
      cam_type: form.cam_type,
      url:      form.cam_type === 'ip' ? form.url : '',
      index:    form.cam_type === 'usb' ? Number(form.index) : 0,
      flip:     form.flip,
    }),
    onSuccess: () => {
      showMsg('✓ เพิ่มกล้องแล้ว — restart ระบบเพื่อให้มีผล')
      qc.invalidateQueries({ queryKey: ['cameras-config'] })
      setForm({ name: '', cam_type: 'usb', url: '', index: '0', flip: false })
      setOpen(false)
    },
    onError: (e) => showErr(e.message),
  })

  const delMut = useMutation({
    mutationFn: (id) => deleteCamera(id),
    onSuccess: (_, id) => {
      showMsg(`✓ ลบ ${id} แล้ว — restart ระบบเพื่อให้มีผล`)
      qc.invalidateQueries({ queryKey: ['cameras-config'] })
    },
    onError: (e) => showErr(e.message),
  })

  const inp = { fontFamily: 'var(--font-sans)', fontSize: 13, padding: '6px 8px', borderRadius: 'var(--radius-sm)', background: 'var(--c-bg-input)', border: '1px solid var(--c-border)', color: 'var(--c-text)', width: '100%', outline: 'none' }
  const lbl = { fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--c-text-4)', display: 'block', marginBottom: 4 }

  return (
    <div className="panel">
      <div className="p-head">
        <span className="eb">CAMERAS</span>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            className="sys-btn sys-ghost"
            style={{ padding: '3px 8px', fontSize: 11, width: 'auto', opacity: isAdmin ? 1 : 0.4 }}
            onClick={() => reloadMut.mutate()}
            disabled={!isAdmin}
            title={isAdmin ? "รีเฟรชรายการกล้อง" : "admin เท่านั้น"}
          >
            <svg viewBox="0 0 24 24" style={{ width: 12, height: 12 }}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            Reload
          </button>
          <button
            className="sys-btn sys-ghost"
            style={{ padding: '3px 8px', fontSize: 11, width: 'auto',
                     color: open ? 'var(--c-accent)' : undefined,
                     opacity: isAdmin ? 1 : 0.4 }}
            onClick={() => setOpen(v => !v)}
            disabled={!isAdmin}
            title={isAdmin ? "" : "admin เท่านั้น"}
          >
            {open ? '✕ ปิด' : '+ เพิ่มกล้อง'}
          </button>
        </div>
      </div>

      {/* Camera list */}
      <div className="p-body" style={{ display: 'grid', gap: 6 }}>
        {cameras.length === 0 && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-4)', textAlign: 'center', padding: '8px 0' }}>ไม่มีกล้อง</div>
        )}
        {cameras.map(cam => (
          <div key={cam.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--c-text-2)' }}>
              {cam.name || cam.id}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--c-text-4)' }}>
              {cam.cam_type === 'ip' ? 'IP' : `USB:${cam.index ?? 0}`}
            </span>
            <button
              onClick={() => { if (confirm(`ลบกล้อง "${cam.name}" (${cam.id})?`)) delMut.mutate(cam.id) }}
              disabled={delMut.isPending || !isAdmin}
              style={{ background: 'none', border: 'none', cursor: isAdmin ? 'pointer' : 'not-allowed', color: '#ef4444', padding: '2px 4px', opacity: isAdmin ? 0.6 : 0.25, lineHeight: 1 }}
              onMouseEnter={e => { if (isAdmin) e.currentTarget.style.opacity = '1' }}
              onMouseLeave={e => { if (isAdmin) e.currentTarget.style.opacity = '0.6' }}
              title={isAdmin ? "ลบกล้อง" : "admin เท่านั้น"}
            >
              <svg viewBox="0 0 24 24" style={{ width: 12, height: 12, fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round' }}>
                <path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2"/>
              </svg>
            </button>
          </div>
        ))}

        {/* Add camera form */}
        {open && (
          <div style={{ borderTop: '1px solid var(--c-border-s)', paddingTop: 10, display: 'grid', gap: 8 }}>
            <div>
              <label style={lbl}>ชื่อกล้อง</label>
              <input style={inp} placeholder="เช่น CAM-FRONT" value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            </div>
            <div>
              <label style={lbl}>ประเภท</label>
              <div style={{ display: 'flex', gap: 6 }}>
                {['usb', 'ip'].map(t => (
                  <button key={t} onClick={() => setForm(f => ({ ...f, cam_type: t }))}
                    style={{ ...inp, width: 'auto', flex: 1, textAlign: 'center', cursor: 'pointer',
                      background: form.cam_type === t ? 'var(--c-accent-bg)' : 'var(--c-bg-input)',
                      color:      form.cam_type === t ? 'var(--c-accent)' : 'var(--c-text-3)',
                      borderColor: form.cam_type === t ? 'var(--c-accent-border)' : 'var(--c-border)',
                    }}>
                    {t.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
            {form.cam_type === 'usb' ? (
              <div>
                <label style={lbl}>Index (0, 1, 2…)</label>
                <input style={inp} type="number" min="0" value={form.index}
                  onChange={e => setForm(f => ({ ...f, index: e.target.value }))} />
              </div>
            ) : (
              <div>
                <label style={lbl}>RTSP URL</label>
                <input style={inp} placeholder="rtsp://..." value={form.url}
                  onChange={e => setForm(f => ({ ...f, url: e.target.value }))} />
              </div>
            )}
            <label style={{ ...lbl, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', marginBottom: 0 }}>
              <input type="checkbox" checked={form.flip} onChange={e => setForm(f => ({ ...f, flip: e.target.checked }))} />
              Flip กล้อง
            </label>
            <button
              className="sys-btn sys-start"
              disabled={!form.name || addMut.isPending}
              onClick={() => addMut.mutate()}
            >
              {addMut.isPending ? 'กำลังเพิ่ม...' : '+ เพิ่มกล้อง'}
            </button>
          </div>
        )}

        {msg && (
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, padding: '5px 8px', borderRadius: 4,
            background: msg.startsWith('✓') ? 'rgba(34,197,94,0.10)' : 'rgba(239,68,68,0.10)',
            color:      msg.startsWith('✓') ? '#22c55e' : '#ef4444',
            border:     `1px solid ${msg.startsWith('✓') ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}`,
          }}>{msg}</div>
        )}
      </div>
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

function PersonPanelCard({ camId, camName, name, person, onFaceClick }) {
  // per_id เต็ม (ไว้ lookup External API) — name prop = masked form
  const perId    = person.per_id || ''
  const maskedId = person.per_id_masked || name

  // ดึงข้อมูลพนักงาน (รวม per_picpath) จาก External API ผ่าน backend proxy
  const { data: personInfo } = useQuery({
    queryKey: ['person', perId],
    queryFn:  () => fetchPerson(perId),
    enabled:  !!perId,
    staleTime: 10 * 60 * 1000,
  })
  const photoUrl = personInfo?.per_picpath || ''
  const [imgFailed, setImgFailed] = useState(false)
  useEffect(() => { setImgFailed(false) }, [photoUrl])

  const elapsed = elapsedSec(person.first_seen)
  const st = person.checked_out
    ? { label: 'ออกงาน',        cls: 'out',      color: '#f97316' }
    : person.checked_in
    ? { label: 'เข้างาน',       cls: '',         color: '#22c55e' }
    : elapsed > SCAN_TIMEOUT_SEC
    ? { label: 'สแกนไม่สำเร็จ', cls: 'fail',     color: '#ef4444' }
    : { label: 'กำลังสแกน',     cls: 'scanning', color: '#eab308' }

  const displayName = person.display_name || maskedId
  const initial = (displayName[0] || '?').toUpperCase()
  const hasPhoto = photoUrl && !imgFailed
  const hasLast  = person.last_seen && person.last_seen !== '-'

  return (
    <div className={`person ${st.cls}`}>
      {/* face area — 52x52, คลิกขยายได้ถ้ามีรูป */}
      <div
        className="face"
        style={{ width: 52, height: 52, cursor: hasPhoto ? 'zoom-in' : 'default' }}
        onClick={() => hasPhoto && onFaceClick?.({ src: photoUrl, name: displayName })}
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
            width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600,
            color: 'var(--c-text-3)', background: 'var(--c-bg-deep)',
          }}>
            {initial}
          </div>
        )}
      </div>
      <div className="info">
        <div className="pname">{displayName}</div>
        <div className="pmeta">
          <span style={{ color: st.color }}>• {st.label}</span>
          <span>📷 {camName || camId}</span>
        </div>
      </div>
      {(person.first_seen && person.first_seen !== '-') && (
        <div className="ptime" style={{ textAlign: 'right', lineHeight: 1.2 }}>
          <div>{person.first_seen.slice(0, 5)}</div>
          {hasLast && (
            <div style={{ fontSize: 9, color: 'var(--c-text-4)', fontFamily: 'var(--font-mono)' }}>
              last {person.last_seen.slice(0, 5)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── DiscordView — main view + thumbnail overlay strip ────────────────────────

function DiscordView({ cameras, selectedCam, selectedCamId, allStates, connectingCams, onSelectCam, onExpand }) {
  const isOnline = selectedCam ? !!allStates[selectedCam?.id] : false
  const isIdle   = selectedCam ? !!allStates[selectedCam?.id]?.idle : false

  if (!selectedCam) return null

  return (
    <div className="discord-layout">
      {/* ── Main view ── */}
      <div className="discord-main discord-main-anim">
        {isOnline ? (
          /* CamStream — snapshot polling ไม่มีปัญหา connection เมื่อสลับกล้อง */
          <CamStream
            key={selectedCam.id}
            camId={selectedCam.id}
            style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block', pointerEvents: 'none' }}
          />
        ) : (
          /* offline / connecting placeholder */
          <div style={{ width: '100%', aspectRatio: '16/9', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, background: '#0a0a0a' }}>
            {connectingCams[selectedCam.id] ? (
              <>
                <svg style={{ width: 24, height: 24, animation: 'spin 0.9s linear infinite', stroke: 'rgba(234,179,8,0.7)', fill: 'none', strokeWidth: 2 }} viewBox="0 0 24 24">
                  <path d="M12 2a10 10 0 0 1 0 20A10 10 0 0 1 2 12" strokeLinecap="round"/>
                </svg>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'rgba(234,179,8,0.5)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Try connect · please wait</span>
              </>
            ) : (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'rgba(239,68,68,0.35)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Camera Offline</span>
            )}
          </div>
        )}

        {/* LIVE / IDLE badge */}
        {isOnline && (
          <div className="badge" style={{
            position: 'absolute', top: 8, left: 8,
            background: isIdle ? 'rgba(99,102,241,0.85)' : undefined,
          }}>
            {isIdle ? 'IDLE' : 'LIVE'}
          </div>
        )}

        {/* Camera name pill — เลื่อนขึ้นจาก thumbnail strip */}
        <div className="discord-cam-label">
          <span className="dot-live" />
          {selectedCam.name || selectedCam.id}
        </div>

        {/* Fullscreen button */}
        <button className="discord-fs-btn" onClick={() => onExpand(selectedCam)} title="เต็มจอ">
          <svg viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 20.25h-4.5m4.5 0v-4.5m0 4.5L15 15"/>
          </svg>
        </button>
      </div>

      {/* Thumbnail strip — อยู่ด้านล่าง main view แยกออกมา */}
      {cameras.length > 1 && (
        <div className="discord-thumbs">
          {cameras.map(cam => (
            <div
              key={cam.id}
              className={`discord-thumb${cam.id === selectedCamId ? ' active' : ''}`}
              onClick={() => onSelectCam(cam.id)}
              title={cam.name || cam.id}
            >
              {cam.id === selectedCamId ? (
                <div className="discord-thumb-selected">▶ MAIN</div>
              ) : (
                <CameraCell
                  cam={cam}
                  isOnline={!!allStates[cam.id]}
                  isIdle={!!allStates[cam.id]?.idle}
                  isConnecting={!allStates[cam.id] && !!connectingCams[cam.id]}
                  onExpand={onExpand}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── CamGrid — responsive grid ที่เต็มพื้นที่ ─────────────────────────────────

function CamGrid({ cameras, allStates, connectingCams, onExpand, onSelect }) {
  const n    = cameras.length
  const cols = n === 1 ? 1 : n <= 4 ? 2 : n <= 9 ? 3 : 4

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${cols}, 1fr)`,
        gap: 6,
        animation: 'camFadeIn 0.22s cubic-bezier(0.22,0.61,0.36,1)',
      }}
    >
      {cameras.map(cam => (
        <CameraCell
          key={cam.id}
          cam={cam}
          isOnline={!!allStates[cam.id]}
          isIdle={!!allStates[cam.id]?.idle}
          isConnecting={!allStates[cam.id] && !!connectingCams[cam.id]}
          onExpand={onExpand}
          onSelect={onSelect}
        />
      ))}
    </div>
  )
}

// ─── Main ──────────────────────────────────────────────────────────────────────

export default function LiveCam() {
  const [allStates,      setAllStates]      = useState({})
  const [fullscreenCam,  setFullscreenCam]  = useState(null)
  const [faceModal,      setFaceModal]      = useState(null)   // { src, name }
  const [cacheBust,      setCacheBust]      = useState(() => Date.now())
  const [selectedCamId,  setSelectedCamId]  = useState(null)
  const [viewMode,       setViewMode]       = useState('grid') // 'grid' | 'discord'
  const [connectingCams, setConnectingCams] = useState({})     // camId → true เมื่อกำลัง connect
  const pollRef = useRef(null)

  const { data: sys = { face: false, api: false } } = useQuery({
    queryKey:        ['sys-status'],
    queryFn:         fetchSystemStatus,
    refetchInterval: 2000,
  })

  const handleClearDone = useCallback(() => {
    setCacheBust(Date.now())
  }, [])

  // เมื่อกด Start ให้ทุกกล้องเข้าสู่ connecting state
  const handleStart = useCallback((camList) => {
    const map = {}
    camList.forEach(c => { map[c.id] = true })
    setConnectingCams(map)
  }, [])

  // เมื่อคลิกกล้องในโหมด grid → เปลี่ยนไป discord mode กล้องนั้น
  const handleCamSelect = useCallback((cam) => {
    setSelectedCamId(cam.id)
    setViewMode('discord')
  }, [])

  // cacheBust ทุก 3 วิ → บังคับรูปโหลดใหม่
  useEffect(() => {
    const t = setInterval(() => setCacheBust(Date.now()), 3000)
    return () => clearInterval(t)
  }, [])

  // Connecting timeout 90 วิ — ถ้าเชื่อมไม่ติดให้เปลี่ยนเป็น offline เอง
  useEffect(() => {
    if (Object.keys(connectingCams).length === 0) return
    const t = setTimeout(() => setConnectingCams({}), 90_000)
    return () => clearTimeout(t)
  }, [connectingCams])

  // Camera list
  const { data: cameras = [] } = useQuery({
    queryKey: ['cameras-config'],
    queryFn:  fetchCameras,
    refetchInterval: 5000,
  })

  // Poll camera states — 1 วิเมื่อระบบรัน, 5 วิเมื่อ Stop
  const sysFaceRef = useRef(sys.face)
  useEffect(() => { sysFaceRef.current = sys.face }, [sys.face])

  const pollStates = useCallback(async () => {
    if (!cameras.length) {
      pollRef.current = setTimeout(pollStates, 500)
      return
    }
    const running = sysFaceRef.current
    const results = await Promise.allSettled(cameras.map(c => fetchCamState(c.id)))
    setAllStates(prev => {
      const next = { ...prev }
      cameras.forEach((c, i) => {
        const res = results[i]
        if (res.status === 'fulfilled' && res.value && isFresh(res.value))
          next[c.id] = res.value
        else
          delete next[c.id]
      })
      return next
    })
    // ล้าง connecting state เมื่อกล้องมาออนไลน์แล้ว
    setConnectingCams(prev => {
      const hasPending = cameras.some(c => prev[c.id])
      if (!hasPending) return prev
      const next = { ...prev }
      cameras.forEach((c, i) => {
        const res = results[i]
        if (res.status === 'fulfilled' && res.value && isFresh(res.value))
          delete next[c.id]
      })
      return next
    })
    pollRef.current = setTimeout(pollStates, running ? 1000 : 5000)
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

  // Auto-select first camera; keep selection if it still exists
  useEffect(() => {
    if (cameras.length === 0) return
    setSelectedCamId(prev =>
      prev && cameras.find(c => c.id === prev) ? prev : cameras[0].id
    )
  }, [cameras])

  const selectedCam  = cameras.find(c => c.id === selectedCamId) || cameras[0] || null
  const activeCamCount = cameras.filter(c => !!allStates[c.id]).length

  return (
    <>
      {fullscreenCam && (
        <FullscreenModal cam={fullscreenCam} onClose={() => setFullscreenCam(null)} />
      )}
      {faceModal && (
        <FaceModal src={faceModal.src} name={faceModal.name} onClose={() => setFaceModal(null)} />
      )}

      <div className="page">

        {/* ── Header ─────────────────────────────────────────────────────────── */}
        <div className="page-head">
          <div>
            <div className="eb" style={{ marginBottom: 6 }}>LIVE · FACE RECOGNITION</div>
            <div className="h1">ภาพจากกล้อง real-time</div>
            <div className="sub">
              {cameras.length} cameras · InsightFace buffalo_l · anti-spoofing pipeline active
            </div>
          </div>
          <div className="status">
            <span className="dot" style={{ background: activeCamCount === 0 ? '#ef4444' : undefined }} />
            system active · {activeCamCount} cam{activeCamCount !== 1 ? 's' : ''} online
          </div>
        </div>

        {/* ── Camera Grid + Right Rail ────────────────────────────────────────── */}
        <div className="two-col">

          {/* Camera area wrapper */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0, minHeight: 0, alignSelf: 'stretch' }}>

            {/* Toolbar: back button (discord mode only) */}
            {viewMode === 'discord' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  onClick={() => setViewMode('grid')}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '4px 10px', borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--c-border)',
                    background: 'transparent', color: 'var(--c-text-3)',
                    cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11,
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--c-bg-hover)'; e.currentTarget.style.color = 'var(--c-text)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--c-text-3)' }}
                >
                  <svg style={{ width: 12, height: 12 }} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7"/>
                  </svg>
                  Grid view
                </button>
              </div>
            )}

            {cameras.length === 0 ? (
              <div style={{
                background: 'var(--c-bg-card)', border: '1px solid var(--c-border)',
                borderRadius: 'var(--radius-sm)', aspectRatio: '16/9',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <div style={{ textAlign: 'center' }}>
                  <p className="eb eb-muted" style={{ marginBottom: 4 }}>ไม่พบกล้อง</p>
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-4)' }}>
                    ตรวจสอบ cameras.json
                  </p>
                </div>
              </div>
            ) : viewMode === 'grid' ? (
              /* ── Grid mode ─────────────────────────────────────── */
              <CamGrid cameras={cameras} allStates={allStates} connectingCams={connectingCams} onExpand={setFullscreenCam} onSelect={handleCamSelect} />
            ) : (
              /* ── Discord mode ──────────────────────────────────── */
              <DiscordView
                cameras={cameras}
                selectedCam={selectedCam}
                selectedCamId={selectedCamId}
                allStates={allStates}
                connectingCams={connectingCams}
                onSelectCam={setSelectedCamId}
                onExpand={setFullscreenCam}
              />
            )}
          </div>

          {/* Right Rail */}
          <div className="rail">

            {/* System Controls Panel */}
            <SystemControls onStart={handleStart} onClearDone={handleClearDone} cameras={cameras} />

            {/* Last Seen Panel */}
            <div className="panel">
              <div className="p-head">
                <span className="eb">LAST SEEN</span>
                <span className="eb eb-muted">{allPersons.length} คน</span>
              </div>
              <div className="p-body" style={{ padding: 10 }}>
                {allPersons.length === 0 ? (
                  <div style={{ textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-4)', padding: '12px 0' }}>
                    ไม่พบใบหน้า
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 280, overflowY: 'auto' }}>
                    {allPersons.map(({ camId, camName, name, person }) => (
                      <PersonPanelCard
                        key={`${camId}-${name}`}
                        camId={camId} camName={camName}
                        name={name} person={person}
                        onFaceClick={setFaceModal}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Camera Manager Panel (list + add + delete + reload) */}
            <CameraManager cameras={cameras} onReload={() => {}} />

            {/* Hints Panel */}
            <div className="panel">
              <div className="p-head">
                <span className="eb">HINTS</span>
                <span className="eb eb-muted">keyboard</span>
              </div>
              <div className="p-body" style={{ display: 'grid', gap: 8, fontSize: 11, color: 'var(--c-text-3)' }}>
                {[['F','เต็มจอ'],['ESC','ออกจากเต็มจอ']].map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className="kbd">{k}</span>
                    <span>{v}</span>
                  </div>
                ))}
              </div>
            </div>

          </div>
        </div>

      </div>
    </>
  )
}
