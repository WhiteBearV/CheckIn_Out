import { NavLink } from 'react-router-dom'
import { useTheme } from '../context/ThemeContext'

const navItems = [
  {
    to: '/',
    label: 'Live Cam',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M15 10l4.553-2.069A1 1 0 0121 8.876V15.124a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
      </svg>
    ),
  },
  {
    to: '/dashboard',
    label: 'Dashboard',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
      </svg>
    ),
  },
  {
    to: '/history',
    label: 'ประวัติลงเวลา',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
    ),
  },
  {
    to: '/reports',
    label: 'รายงาน',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
]

export default function Sidebar() {
  const { theme, toggleTheme } = useTheme()

  return (
    <aside
      className="w-56 min-h-screen flex flex-col"
      style={{
        background:   'var(--c-bg-card)',
        borderRight:  '1px solid var(--c-border)',
        transition:   'background 0.2s',
      }}
    >
      {/* ── Logo ─────────────────────────────────────────── */}
      <div
        className="h-14 flex items-center gap-2.5 px-5"
        style={{ borderBottom: '1px solid var(--c-border)' }}
      >
        <div className="w-2 h-2 rounded-full" style={{ background: 'var(--c-accent)' }} />
        <span className="font-mono text-sm tracking-tight" style={{ color: 'var(--c-text)' }}>
          Face Attendance
        </span>
      </div>

      {/* ── Navigation ───────────────────────────────────── */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        <p
          className="font-mono text-[10px] uppercase tracking-widest px-2 pb-2"
          style={{ color: 'var(--c-text-4)' }}
        >
          Navigation
        </p>

        {navItems.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/' || item.to === '/live'}
            style={({ isActive }) => ({
              display:        'flex',
              alignItems:     'center',
              gap:            10,
              padding:        '8px 8px',
              borderRadius:   6,
              fontSize:       14,
              textDecoration: 'none',
              transition:     'background 0.15s, color 0.15s',
              background:     isActive ? 'var(--c-accent-bg)' : 'transparent',
              color:          isActive ? 'var(--c-accent)' : 'var(--c-text-2)',
            })}
          >
            {({ isActive }) => (
              <>
                <span style={{ color: isActive ? 'var(--c-accent)' : 'var(--c-text-3)' }}>
                  {item.icon}
                </span>
                <span className="font-sans">{item.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* ── Theme toggle ─────────────────────────────────── */}
      <div className="p-3" style={{ borderTop: '1px solid var(--c-border)' }}>
        <button
          onClick={toggleTheme}
          className="w-full flex items-center gap-2.5 px-2 py-2 rounded text-sm transition-colors"
          style={{ color: 'var(--c-text-3)' }}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--c-bg-hover)'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
        >
          {theme === 'dark' ? (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z" />
              </svg>
              <span className="font-mono text-xs">Light Mode</span>
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
              <span className="font-mono text-xs">Dark Mode</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}
