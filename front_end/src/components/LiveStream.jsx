import { useEffect, useRef, useState } from 'react'

const POLL_INTERVAL = 5000 // ตรวจสอบ status ทุก 5 วินาทีเมื่อ offline

export default function LiveStream() {
  const [streamStatus, setStreamStatus] = useState('connecting') // 'connecting' | 'active' | 'offline'
  const imgRef    = useRef(null)
  const timerRef  = useRef(null)

  // ตรวจ /status เพื่อรู้ว่า main.py รันอยู่ไหม
  const checkStatus = async () => {
    try {
      const res = await fetch('/status', { signal: AbortSignal.timeout(2000) })
      if (!res.ok) throw new Error()
      const data = await res.json()
      if (data.ready) {
        setStreamStatus('active')
      } else {
        setStreamStatus('connecting')
      }
    } catch {
      setStreamStatus('offline')
    }
  }

  useEffect(() => {
    checkStatus()
    timerRef.current = setInterval(checkStatus, POLL_INTERVAL)
    return () => clearInterval(timerRef.current)
  }, [])

  // เมื่อ stream โหลดสำเร็จ → หยุด polling (ประหยัด request)
  const handleLoad = () => {
    setStreamStatus('active')
    clearInterval(timerRef.current)
  }

  const handleError = () => {
    setStreamStatus('offline')
    // เริ่ม retry polling อีกรอบ
    clearInterval(timerRef.current)
    timerRef.current = setInterval(checkStatus, POLL_INTERVAL)
  }

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-slate-800 dark:text-white">Live Camera</h2>
          <StatusDot status={streamStatus} />
        </div>
        <span className="text-xs text-slate-400 dark:text-slate-500 font-mono">
          {streamStatus === 'active' ? 'LIVE' : streamStatus === 'connecting' ? 'กำลังเชื่อมต่อ...' : 'ไม่มีสัญญาณ'}
        </span>
      </div>

      {/* Stream Area */}
      <div className="relative bg-black" style={{ aspectRatio: '16/9' }}>
        {/* MJPEG Image */}
        {streamStatus !== 'offline' && (
          <img
            ref={imgRef}
            src="/stream"
            alt="Live camera feed"
            className="w-full h-full object-contain"
            onLoad={handleLoad}
            onError={handleError}
          />
        )}

        {/* Overlay states */}
        {streamStatus === 'connecting' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/80">
            <div className="w-10 h-10 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-3" />
            <p className="text-sm text-slate-300">กำลังเชื่อมต่อกล้อง...</p>
            <p className="text-xs text-slate-500 mt-1">รอ main.py เริ่มทำงาน</p>
          </div>
        )}

        {streamStatus === 'offline' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-950">
            <svg className="w-14 h-14 text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M15 10l4.553-2.069A1 1 0 0121 8.876V15.124a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M3 3l18 18" />
            </svg>
            <p className="text-sm text-slate-400">ไม่ได้รับสัญญาณ</p>
            <p className="text-xs text-slate-600 mt-1">รัน main.py เพื่อเริ่ม stream</p>
          </div>
        )}
      </div>
    </div>
  )
}

function StatusDot({ status }) {
  if (status === 'active') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-green-500">
        <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
        Live
      </span>
    )
  }
  if (status === 'connecting') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-yellow-500">
        <span className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
        Connecting
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-500">
      <span className="w-2 h-2 rounded-full bg-slate-500" />
      Offline
    </span>
  )
}
