import { useRef, useState, useEffect, useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import { useTheme } from '../context/ThemeContext'
import { useAuth } from '../context/AuthContext'


const NAV = [
  {
    to: '/',
    label: 'Live Cam',
    icon: <svg viewBox="0 0 24 24"><path d="M15 10l4.553-2.069A1 1 0 0121 8.876V15.124a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z"/></svg>,
  },
  {
    to: '/dashboard',
    label: 'Dashboard',
    icon: <svg viewBox="0 0 24 24"><path d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"/></svg>,
  },
  {
    to: '/history',
    label: 'ประวัติลงเวลา',
    icon: <svg viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>,
  },
  {
    to: '/reports',
    label: 'รายงาน',
    icon: <svg viewBox="0 0 24 24"><path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>,
  },
]

const MIN_W = 160
const MAX_W = 320
const DEFAULT_W = 224

export default function Sidebar() {
  const { theme, toggleTheme } = useTheme()
  const { user, logout } = useAuth()
  const [width, setWidth] = useState(() => {
    const saved = localStorage.getItem('sb-width')
    return saved ? Number(saved) : DEFAULT_W
  })
  const dragging = useRef(false)
  const startX   = useRef(0)
  const startW   = useRef(0)

  const onMouseDown = useCallback((e) => {
    dragging.current = true
    startX.current   = e.clientX
    startW.current   = width
    document.body.style.cursor    = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [width])

  useEffect(() => {
    const onMove = (e) => {
      if (!dragging.current) return
      const delta = e.clientX - startX.current
      const next  = Math.min(MAX_W, Math.max(MIN_W, startW.current + delta))
      setWidth(next)
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.style.cursor    = ''
      document.body.style.userSelect = ''
      setWidth(w => { localStorage.setItem('sb-width', w); return w })
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup',   onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup',   onUp)
    }
  }, [])

  return (
    <aside className="sidebar" style={{ width }}>
      {/* Logo */}
      <div className="sb-logo">
        <img src="/logo-mark.svg" alt="" style={{ width: 28, height: 28, flexShrink: 0 }} />
        <div className="wm">Face Attendance</div>
      </div>

      {/* Nav */}
      <nav className="sb-nav">
        {NAV.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => 'sb-item' + (isActive ? ' active' : '')}
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* User + Theme + Logout */}
      <div className="sb-foot" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {user && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 10px',
            borderRadius: 6,
            background: 'var(--c-accent-bg)',
            border: '1px solid var(--c-accent-border)',
            fontSize: 12, color: 'var(--c-text-1)',
            overflow: 'hidden',
          }} title={`${user.username} (${user.role})`}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%',
              background: user.role === 'admin' ? 'var(--c-accent)' : '#888',
              flexShrink: 0,
            }} />
            <div style={{
              display: 'flex', flexDirection: 'column',
              minWidth: 0, flex: 1,
            }}>
              <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user.username}
              </span>
              <span style={{ fontSize: 10, color: 'var(--c-text-3)', textTransform: 'uppercase', letterSpacing: 1 }}>
                {user.role}
              </span>
            </div>
          </div>
        )}

        <button className="sb-theme" onClick={toggleTheme}>
          {theme === 'dark' ? (
            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 3v1M12 20v1M3 12h1M20 12h1M5.6 5.6l.7.7M17.7 17.7l.7.7M5.6 18.4l.7-.7M17.7 6.3l.7-.7"/></svg>
          ) : (
            <svg viewBox="0 0 24 24"><path d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>
          )}
          {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
        </button>

        {user && (
          <button className="sb-theme" onClick={logout}
            style={{ color: '#ff8a8a' }}>
            <svg viewBox="0 0 24 24"><path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>
            ออกจากระบบ
          </button>
        )}
      </div>

      {/* Resize handle */}
      <div className="sb-resize" onMouseDown={onMouseDown} />
    </aside>
  )
}
