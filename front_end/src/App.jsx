import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, useEffect, useRef, useCallback } from 'react'
import { ThemeProvider } from './context/ThemeContext'
import { AuthProvider, RequireAuth } from './context/AuthContext'
import Sidebar from './components/Sidebar'
import LiveCam from './pages/LiveCam'
import Dashboard from './pages/Dashboard'
import History from './pages/History'
import Report from './pages/Report'
import Login from './pages/Login'
import ChangePassword from './pages/ChangePassword'
import Users from './pages/Users'

const CLOCK_POS_KEY = 'clock_pos'

function Clock() {
  const [now, setNow] = useState(new Date())
  const [pos, setPos] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(CLOCK_POS_KEY))
      if (saved && typeof saved.x === 'number') return saved
    } catch {}
    return null  // null = ใช้ default bottom-right
  })
  const [dragging, setDragging] = useState(false)
  const dragOffset = useRef({ dx: 0, dy: 0 })
  const ref = useRef(null)

  // tick
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const onMouseDown = useCallback(e => {
    if (e.button !== 0) return
    e.preventDefault()
    const rect = ref.current.getBoundingClientRect()
    dragOffset.current = { dx: e.clientX - rect.left, dy: e.clientY - rect.top }
    setDragging(true)
  }, [])

  useEffect(() => {
    if (!dragging) return
    const onMove = e => {
      const x = Math.max(0, Math.min(window.innerWidth  - (ref.current?.offsetWidth  || 0), e.clientX - dragOffset.current.dx))
      const y = Math.max(0, Math.min(window.innerHeight - (ref.current?.offsetHeight || 0), e.clientY - dragOffset.current.dy))
      const next = { x, y }
      setPos(next)
      localStorage.setItem(CLOCK_POS_KEY, JSON.stringify(next))
    }
    const onUp = () => setDragging(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup',   onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup',   onUp)
    }
  }, [dragging])

  const time = now.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const date = now.toLocaleDateString('th-TH', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })

  const posStyle = pos
    ? { top: pos.y, left: pos.x }
    : { bottom: 16, right: 16 }

  return (
    <div
      ref={ref}
      onMouseDown={onMouseDown}
      style={{
        position:     'fixed',
        ...posStyle,
        zIndex:       9000,
        display:      'flex',
        alignItems:   'center',
        gap:          10,
        padding:      '6px 14px',
        borderRadius: 8,
        background:   'var(--c-accent-bg)',
        border:       '1px solid var(--c-accent-border)',
        backdropFilter: 'blur(8px)',
        boxShadow:    '0 2px 12px rgba(0,0,0,0.18)',
        fontFamily:   'var(--font-mono)',
        userSelect:   'none',
        cursor:       dragging ? 'grabbing' : 'grab',
        touchAction:  'none',
      }}
    >
      <span style={{
        width: 6, height: 6, borderRadius: '50%',
        background: 'var(--c-accent)',
        animation: 'blink 1s infinite',
        flexShrink: 0,
      }} />
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
        <span style={{ fontSize: 24, fontWeight: 700, color: 'var(--c-accent)', letterSpacing: '0.06em', lineHeight: 1 }}>
          {time}
        </span>
        <span style={{ fontSize: 16, color: 'var(--c-text-3)', letterSpacing: '0.04em', lineHeight: 1.2 }}>
          {date}
        </span>
      </div>
    </div>
  )
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: 1,
    },
  },
})

function PlaceholderPage({ title }) {
  return (
    <div className="p-8 flex items-center justify-center h-full">
      <div className="text-center">
        <p className="font-mono text-xs uppercase tracking-widest mb-3"
          style={{ color: 'var(--c-accent)' }}>
          Coming Soon
        </p>
        <p className="text-xl font-light" style={{ color: 'var(--c-text-2)' }}>{title}</p>
      </div>
    </div>
  )
}

function Layout() {
  return (
    <div className="app">
      <Clock />
      <Sidebar />
      <main className="main">
        <Routes>
          <Route path="/"          element={<LiveCam />} />
          <Route path="/live"      element={<LiveCam />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/history"   element={<History />} />
          <Route path="/reports"   element={<Report />} />
          <Route path="/users"     element={<Users />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              {/* /change-password อยู่ใน RequireAuth (ต้อง login) แต่ไม่อยู่ใน Layout
                  — ไม่แสดง sidebar เพราะคนยังต้องบังคับเปลี่ยนรหัสก่อนใช้ระบบ */}
              <Route path="/change-password" element={
                <RequireAuth><ChangePassword /></RequireAuth>
              } />
              <Route path="/*" element={
                <RequireAuth>
                  <Layout />
                </RequireAuth>
              } />
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
