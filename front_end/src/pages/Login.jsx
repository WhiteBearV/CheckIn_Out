import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { login } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Logo from '../components/Logo'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
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
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            style={inputStyle}
          />
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
          style={{
            padding: '14px 22px', borderRadius: 10,
            background: 'var(--c-accent)', color: '#000',
            border: 'none', fontWeight: 600, fontSize: 24,
            cursor: loading ? 'wait' : 'pointer',
            opacity: (loading || !username || !password) ? 0.55 : 1,
            marginTop: 4,
          }}
        >
          {loading ? 'กำลังเข้าสู่ระบบ…' : 'เข้าสู่ระบบ'}
        </button>

        {/* TODO(production): ลบ block "default credentials" ทั้งก้อนนี้ก่อน deploy
            — เปิดเผย default creds ในหน้า public ไม่ปลอดภัย */}
        <div style={{
          fontSize: 12, color: '#fbbf24',
          background: 'rgba(251,191,36,0.10)',
          border: '1px solid rgba(251,191,36,0.35)',
          borderRadius: 8, padding: '10px 14px',
          textAlign: 'center', lineHeight: 1.5,
        }}>
          ⚠ Dev only — ลบ block นี้ก่อน deploy production
          <div style={{ marginTop: 4, color: 'var(--c-text-3)' }}>
            Default: <code>admin / Admin12345</code> หรือ <code>viewer / User12345</code>
          </div>
        </div>
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
