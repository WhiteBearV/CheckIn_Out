import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { ThemeProvider } from './context/ThemeContext'
import { AuthProvider, RequireAuth } from './context/AuthContext'
import Sidebar from './components/Sidebar'
import LiveCam from './pages/LiveCam'
import Dashboard from './pages/Dashboard'
import History from './pages/History'
import Report from './pages/Report'
import Login from './pages/Login'

function Clock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const time = now.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const date = now.toLocaleDateString('th-TH', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })

  return (
    <div style={{
      position:     'fixed',
      bottom:       16,
      right:        16,
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
      pointerEvents: 'none',
      userSelect:   'none',
    }}>
      {/* pulse dot */}
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
