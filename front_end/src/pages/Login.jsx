import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { login } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Logo from '../components/Logo'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw,   setShowPw]   = useState(false)
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)
  const nav = useNavigate()
  const loc = useLocation()
  const { setUser } = useAuth()

  const from = loc.state?.from || '/'

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await login(username.trim(), password)
      setUser({
        username:             data.username,
        role:                 data.role,
        must_change_password: !!data.must_change_password,
      })
      // บังคับเปลี่ยนรหัสครั้งแรก — ไป /change-password แทน destination ปกติ
      const next = data.must_change_password ? '/change-password' : from
      nav(next, { replace: true })
    } catch (err) {
      setError(err.message || 'ล็อกอินไม่สำเร็จ')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', background: 'var(--c-bg)',
      padding: 24,
    }}>
      <form onSubmit={onSubmit} style={{
        width: '100%', maxWidth: 520,
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border)',
        borderRadius: 16, padding: 56,
        boxShadow: '0 12px 48px rgba(0,0,0,0.22)',
        display: 'flex', flexDirection: 'column', gap: 22,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
          <Logo size={48} />
          <div>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--c-text-1)' }}>
              Face Attendance
            </div>
            <div style={{ fontSize: 20, color: 'var(--c-text-3)', letterSpacing: 1.5, textTransform: 'uppercase' }}>
              Sign in
            </div>
          </div>
        </div>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ fontSize: 24, color: 'var(--c-text-2)' }}>Username</span>
          <input
            type="text"
            value={username}
            onChange={e => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
            required
            style={inputStyle}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ fontSize: 24, color: 'var(--c-text-2)' }}>Password</span>
          <div style={{ position: 'relative', width: '100%' }}>
            <input
              type={showPw ? 'text' : 'password'}
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              style={{ ...inputStyle, width: '100%', boxSizing: 'border-box', paddingRight: 48 }}
            />
            <button type="button" onClick={() => setShowPw(v => !v)}
              style={{
                position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                background: 'none', border: 'none', cursor: 'pointer', padding: 4,
                color: 'var(--c-text-3)', display: 'flex', alignItems: 'center',
              }}>
              {showPw
                ? <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                : <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              }
            </button>
          </div>
        </label>

        {error && (
          <div style={{
            fontSize: 24, color: '#ff6b6b',
            background: 'rgba(255,107,107,0.10)',
            border: '1px solid rgba(255,107,107,0.30)',
            borderRadius: 8, padding: '10px 14px',
          }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !username || !password}
          className="btn btn-primary btn-block"
        >
          {loading ? 'กำลังเข้าสู่ระบบ…' : 'เข้าสู่ระบบ'}
        </button>

      </form>
    </div>
  )
}

const inputStyle = {
  padding: '12px 16px',
  background: 'var(--c-bg)',
  border: '1px solid var(--c-border)',
  borderRadius: 8,
  color: 'var(--c-text-1)',
  fontSize: 24,
  outline: 'none',
}
