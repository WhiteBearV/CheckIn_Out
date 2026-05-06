import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authFetch } from '../api/client'
import { useAuth } from '../context/AuthContext'

export default function ChangePassword() {
  const { user, mustChangePassword, clearMustChange, logout } = useAuth()
  const [oldPw,   setOldPw]   = useState('')
  const [newPw,   setNewPw]   = useState('')
  const [confirm, setConfirm] = useState('')
  const [error,   setError]   = useState('')
  const [loading, setLoading] = useState(false)
  const nav = useNavigate()

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    if (newPw.length < 6)         return setError('password ใหม่ต้องอย่างน้อย 6 ตัวอักษร')
    if (newPw !== confirm)        return setError('ยืนยัน password ไม่ตรงกัน')
    if (newPw === oldPw)          return setError('password ใหม่ต้องไม่ซ้ำกับเดิม')

    setLoading(true)
    try {
      const r = await authFetch('/auth/change-password', {
        method: 'POST',
        body:   { old_password: oldPw, new_password: newPw },
      })
      if (!r.ok) {
        const d = await r.json().catch(() => ({}))
        throw new Error(d.detail || `HTTP ${r.status}`)
      }
      clearMustChange()
      nav('/', { replace: true })
    } catch (err) {
      setError(err.message || 'เปลี่ยนรหัสไม่สำเร็จ')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', background: 'var(--c-bg)', padding: 24,
    }}>
      <form onSubmit={onSubmit} style={{
        width: '100%', maxWidth: 520,
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border)',
        borderRadius: 16, padding: 56,
        boxShadow: '0 12px 48px rgba(0,0,0,0.22)',
        display: 'flex', flexDirection: 'column', gap: 18,
      }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--c-text-1)' }}>
            เปลี่ยนรหัสผ่าน
          </div>
          <div style={{ fontSize: 13, color: 'var(--c-text-3)', marginTop: 6 }}>
            User: <code>{user?.username}</code>
          </div>
        </div>

        {mustChangePassword && (
          <div style={{
            fontSize: 13, color: '#fbbf24',
            background: 'rgba(251,191,36,0.10)',
            border: '1px solid rgba(251,191,36,0.35)',
            borderRadius: 8, padding: '10px 14px', lineHeight: 1.5,
          }}>
            ⚠ บังคับเปลี่ยนรหัสครั้งแรก — ระบบใช้ default password อยู่
            ต้องตั้งใหม่ก่อนเข้าใช้งาน
          </div>
        )}

        <label style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ fontSize: 14, color: 'var(--c-text-2)' }}>รหัสเดิม</span>
          <input type="password" value={oldPw} onChange={e => setOldPw(e.target.value)}
                 autoFocus required style={inputStyle} />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ fontSize: 14, color: 'var(--c-text-2)' }}>รหัสใหม่</span>
          <input type="password" value={newPw} onChange={e => setNewPw(e.target.value)}
                 required minLength={6} style={inputStyle} />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ fontSize: 14, color: 'var(--c-text-2)' }}>ยืนยันรหัสใหม่</span>
          <input type="password" value={confirm} onChange={e => setConfirm(e.target.value)}
                 required minLength={6} style={inputStyle} />
        </label>

        {error && (
          <div style={{
            fontSize: 14, color: '#ff6b6b',
            background: 'rgba(255,107,107,0.10)',
            border: '1px solid rgba(255,107,107,0.30)',
            borderRadius: 8, padding: '10px 14px',
          }}>
            {error}
          </div>
        )}

        <button type="submit" disabled={loading || !oldPw || !newPw || !confirm}
          style={{
            padding: '14px 22px', borderRadius: 10,
            background: 'var(--c-accent)', color: '#000',
            border: 'none', fontWeight: 600, fontSize: 16,
            cursor: loading ? 'wait' : 'pointer',
            opacity: (loading || !oldPw || !newPw || !confirm) ? 0.55 : 1,
            marginTop: 4,
          }}>
          {loading ? 'กำลังเปลี่ยน…' : 'บันทึกรหัสใหม่'}
        </button>

        {!mustChangePassword && (
          <button type="button" onClick={() => nav(-1)}
            style={{
              padding: '10px 16px', background: 'transparent',
              color: 'var(--c-text-3)', border: '1px solid var(--c-border)',
              borderRadius: 8, cursor: 'pointer', fontSize: 13,
            }}>
            ยกเลิก
          </button>
        )}

        {mustChangePassword && (
          <button type="button" onClick={logout}
            style={{
              padding: '10px 16px', background: 'transparent',
              color: 'var(--c-text-3)', border: '1px solid var(--c-border)',
              borderRadius: 8, cursor: 'pointer', fontSize: 13,
            }}>
            ออกจากระบบ
          </button>
        )}
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
  fontSize: 15,
  outline: 'none',
}
