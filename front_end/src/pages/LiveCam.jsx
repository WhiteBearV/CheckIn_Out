import { useEffect, useRef, useState, useCallback } from 'react'

const POLL_INTERVAL = 5000

function StatusDot({ status }) {
  if (status === 'active') {
    return (
      <span className="flex items-center gap-1.5 text-xs font-medium text-green-500">
        <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
        LIVE
      </span>
    )
  }
  if (status === 'connecting') {
    return (
      <span className="flex items-center gap-1.5 text-xs font-medium text-yellow-500">
        <span className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
        กำลังเชื่อมต่อ
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
      <span className="w-2 h-2 rounded-full bg-slate-500" />
      Offline
    </span>
  )
}

export default function LiveCam() {
  const [streamStatus, setStreamStatus] = useState('connecting')
  const [isFullscreen, setIsFullscreen]  = useState(false)
  const containerRef = useRef(null)
  const timerRef     = useRef(null)

  // ─── ตรวจ status ───
  const checkStatus = useCallback(async () => {
    try {
      const res = await fetch('/status', { signal: AbortSignal.timeout(2000) })
      if (!res.ok) throw new Error()
      const data = await res.json()
      setStreamStatus(data.ready ? 'active' : 'connecting')
    } catch {
      setStreamStatus('offline')
    }
  }, [])

  useEffect(() => {
    checkStatus()
    timerRef.current = setInterval(checkStatus, POLL_INTERVAL)
    return () => clearInterval(timerRef.current)
  }, [checkStatus])

  // ─── Fullscreen API ───
  const toggleFullscreen = useCallback(async () => {
    if (!document.fullscreenElement) {
      await containerRef.current?.requestFullscreen()
    } else {
      await document.exitFullscreen()
    }
  }, [])

  useEffect(() => {
    const onFsChange = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', onFsChange)
    return () => document.removeEventListener('fullscreenchange', onFsChange)
  }, [])

  // ─── Keyboard shortcut: F = fullscreen, ESC handled by browser ───
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'f' || e.key === 'F') toggleFullscreen()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggleFullscreen])

  const handleLoad  = () => {
    setStreamStatus('active')
    clearInterval(timerRef.current)
  }
  const handleError = () => {
    setStreamStatus('offline')
    clearInterval(timerRef.current)
    timerRef.current = setInterval(checkStatus, POLL_INTERVAL)
  }

  return (
    <div className="p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-white flex items-center gap-2">
            <svg className="w-6 h-6 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M15 10l4.553-2.069A1 1 0 0121 8.876V15.124a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
            </svg>
            Live Cam
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            ภาพ real-time จากระบบตรวจใบหน้า
          </p>
        </div>
        <StatusDot status={streamStatus} />
      </div>

      {/* Stream container */}
      <div
        ref={containerRef}
        className="
          relative bg-black rounded-xl overflow-hidden
          border border-slate-200 dark:border-slate-700
          group
        "
        style={{ aspectRatio: isFullscreen ? 'auto' : '16/9' }}
      >
        {/* MJPEG stream */}
        {streamStatus !== 'offline' && (
          <img
            src="/stream"
            alt="Live camera feed"
            className={`
              ${isFullscreen
                ? 'w-full h-full object-contain'
                : 'w-full h-full object-contain'
              }
            `}
            onLoad={handleLoad}
            onError={handleError}
          />
        )}

        {/* Connecting overlay */}
        {streamStatus === 'connecting' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/80">
            <div className="w-12 h-12 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-slate-300 font-medium">กำลังเชื่อมต่อกล้อง...</p>
            <p className="text-slate-500 text-sm mt-1">รอ main.py เริ่มทำงาน</p>
          </div>
        )}

        {/* Offline overlay */}
        {streamStatus === 'offline' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-950">
            <svg className="w-16 h-16 text-slate-700 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M15 10l4.553-2.069A1 1 0 0121 8.876V15.124a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
              <line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" />
            </svg>
            <p className="text-slate-400 font-medium">ไม่ได้รับสัญญาณ</p>
            <p className="text-slate-600 text-sm mt-1">รัน main.py เพื่อเริ่ม stream</p>
            <button
              onClick={checkStatus}
              className="mt-4 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm transition-colors"
            >
              ลองใหม่
            </button>
          </div>
        )}

        {/* Fullscreen button — โชว์เมื่อ hover */}
        <button
          onClick={toggleFullscreen}
          title={isFullscreen ? 'ออกจากเต็มจอ (Esc)' : 'เต็มจอ (F)'}
          className="
            absolute bottom-4 right-4
            p-2 rounded-lg
            bg-black/50 hover:bg-black/80
            text-white
            opacity-0 group-hover:opacity-100
            transition-opacity duration-200
          "
        >
          {isFullscreen ? (
            /* compress icon */
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
            </svg>
          ) : (
            /* expand icon */
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
            </svg>
          )}
        </button>

        {/* LIVE badge (มุมบนซ้าย) — แสดงเฉพาะตอน active */}
        {streamStatus === 'active' && (
          <div className="absolute top-4 left-4 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-600/90 text-white text-xs font-bold tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            LIVE
          </div>
        )}

        {/* Keyboard hint */}
        {!isFullscreen && streamStatus === 'active' && (
          <div className="absolute bottom-4 left-4 text-xs text-white/40 opacity-0 group-hover:opacity-100 transition-opacity">
            กด F เพื่อเต็มจอ
          </div>
        )}
      </div>
    </div>
  )
}
