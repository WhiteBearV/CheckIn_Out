import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listUsers, addUser, deleteUser, resetUserPassword, updateUserRole } from '../api/client'
import { useAuth } from '../context/AuthContext'
import ConfirmModal from '../components/ConfirmModal'

const inputStyle = {
  padding: '16px 20px',
  background: 'var(--c-bg)',
  border: '1px solid var(--c-border)',
  borderRadius: 8,
  color: 'var(--c-text-1)',
  fontSize: 22,
  outline: 'none',
  width: '100%',
  boxSizing: 'border-box',
}

const btnClass = {
  primary: 'btn btn-primary',
  danger:  'btn btn-stop',
  ghost:   'btn btn-ghost',
  warn:    'btn btn-blue',
}

function Modal({ title, onClose, children }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)',
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        width: '100%', maxWidth: 420,
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border)',
        borderRadius: 16, padding: 32,
        boxShadow: '0 16px 56px rgba(0,0,0,0.35)',
        display: 'flex', flexDirection: 'column', gap: 16,
      }}>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--c-text-1)' }}>{title}</div>
        {children}
      </div>
    </div>
  )
}

function AddUserModal({ onClose, onSuccess }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role,     setRole]     = useState('viewer')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    if (username.trim().length < 3) return setError('username ต้องอย่างน้อย 3 ตัวอักษร')
    if (password.length < 6)        return setError('password ต้องอย่างน้อย 6 ตัวอักษร')
    setLoading(true)
    try {
      await addUser(username.trim(), password, role)
      onSuccess()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal title="เพิ่มผู้ใช้ใหม่" onClose={onClose}>
      <form onSubmit={onSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 16, color: 'var(--c-text-3)', textTransform: 'uppercase', letterSpacing: 1 }}>Username</span>
          <input style={inputStyle} value={username} onChange={e => setUsername(e.target.value)}
                 autoFocus required minLength={3} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 16, color: 'var(--c-text-3)', textTransform: 'uppercase', letterSpacing: 1 }}>Password</span>
          <input style={inputStyle} type="password" value={password}
                 onChange={e => setPassword(e.target.value)} required minLength={6} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 16, color: 'var(--c-text-3)', textTransform: 'uppercase', letterSpacing: 1 }}>Role</span>
          <select style={{ ...inputStyle }} value={role} onChange={e => setRole(e.target.value)}>
            <option value="viewer">viewer</option>
            <option value="admin">admin</option>
          </select>
        </label>
        {error && (
          <div style={{ fontSize: 18, color: '#ff6b6b', background: 'rgba(255,107,107,0.10)',
                        border: '1px solid rgba(255,107,107,0.25)', borderRadius: 8, padding: '8px 12px' }}>
            {error}
          </div>
        )}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 4 }}>
          <button type="button" className={btnClass.ghost} onClick={onClose}>ยกเลิก</button>
          <button type="submit" className={btnClass.primary} disabled={loading}>
            {loading ? 'กำลังเพิ่ม…' : 'เพิ่มผู้ใช้'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function ResetPasswordModal({ username, onClose, onSuccess }) {
  const [newPw,   setNewPw]   = useState('')
  const [confirm, setConfirm] = useState('')
  const [error,   setError]   = useState('')
  const [loading, setLoading] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    if (newPw.length < 6)    return setError('password ต้องอย่างน้อย 6 ตัวอักษร')
    if (newPw !== confirm)   return setError('ยืนยัน password ไม่ตรงกัน')
    setLoading(true)
    try {
      await resetUserPassword(username, newPw)
      onSuccess()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal title={`รีเซ็ต password — ${username}`} onClose={onClose}>
      <form onSubmit={onSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 16, color: 'var(--c-text-3)', textTransform: 'uppercase', letterSpacing: 1 }}>Password ใหม่</span>
          <input style={inputStyle} type="password" value={newPw}
                 onChange={e => setNewPw(e.target.value)} autoFocus required minLength={6} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 16, color: 'var(--c-text-3)', textTransform: 'uppercase', letterSpacing: 1 }}>ยืนยัน Password</span>
          <input style={inputStyle} type="password" value={confirm}
                 onChange={e => setConfirm(e.target.value)} required minLength={6} />
        </label>
        {error && (
          <div style={{ fontSize: 18, color: '#ff6b6b', background: 'rgba(255,107,107,0.10)',
                        border: '1px solid rgba(255,107,107,0.25)', borderRadius: 8, padding: '8px 12px' }}>
            {error}
          </div>
        )}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 4 }}>
          <button type="button" className={btnClass.ghost} onClick={onClose}>ยกเลิก</button>
          <button type="submit" className={btnClass.warn} disabled={loading}>
            {loading ? 'กำลังรีเซ็ต…' : 'รีเซ็ต Password'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function fmt(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('th-TH', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function Users() {
  const { user: me } = useAuth()
  const qc = useQueryClient()

  const { data: users = [], isLoading, error } = useQuery({
    queryKey: ['users'],
    queryFn: listUsers,
  })

  const deleteMut = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })

  const roleMut = useMutation({
    mutationFn: ({ username, role }) => updateUserRole(username, role),
    onSuccess: (_, { username, role }) => {
      qc.invalidateQueries({ queryKey: ['users'] })
      showToast(`เปลี่ยน role "${username}" เป็น ${role} เรียบร้อย`)
    },
    onError: err => showToast(`เปลี่ยน role ไม่สำเร็จ: ${err.message}`),
  })

  const [showAdd,    setShowAdd]    = useState(false)
  const [resetFor,   setResetFor]   = useState(null)
  const [deleteFor,  setDeleteFor]  = useState(null)
  const [toast,      setToast]      = useState('')

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  async function onDelete(username) {
    try {
      await deleteMut.mutateAsync(username)
      showToast(`ลบ "${username}" เรียบร้อย`)
    } catch (err) {
      showToast(`ลบไม่สำเร็จ: ${err.message}`)
    }
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 900, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--c-text-1)' }}>จัดการผู้ใช้</div>
          <div style={{ fontSize: 24, color: 'var(--c-text-3)', marginTop: 4 }}>
            เพิ่ม / ลบ / รีเซ็ต password ผู้ใช้ในระบบ
          </div>
        </div>
        <button className={btnClass.primary} onClick={() => setShowAdd(true)}>
          + เพิ่มผู้ใช้
        </button>
      </div>

      {/* Toast */}
      {toast && (
        <div style={{
          marginBottom: 16, padding: '10px 16px', borderRadius: 8, fontSize: 18,
          background: 'var(--c-accent-bg)', border: '1px solid var(--c-accent-border)',
          color: 'var(--c-accent)',
        }}>
          {toast}
        </div>
      )}

      {/* Table */}
      <div style={{
        background: 'var(--c-surface)', border: '1px solid var(--c-border)',
        borderRadius: 12, overflow: 'hidden',
      }}>
        {isLoading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--c-text-3)', fontSize: 20 }}>
            กำลังโหลด…
          </div>
        ) : error ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#ff6b6b', fontSize: 14 }}>
            โหลดข้อมูลไม่สำเร็จ
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--c-border)', background: 'var(--c-bg)' }}>
                {['Username', 'Role', 'สร้างเมื่อ', 'Login ล่าสุด', ''].map(h => (
                  <th key={h} style={{
                    padding: '12px 16px', textAlign: 'left',
                    fontSize: 16, fontWeight: 600, color: 'var(--c-text-3)',
                    textTransform: 'uppercase', letterSpacing: '0.08em',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((u, i) => (
                <tr key={u.username} style={{
                  borderBottom: i < users.length - 1 ? '1px solid var(--c-border)' : 'none',
                  opacity: deleteMut.isPending && deleteMut.variables === u.username ? 0.4 : 1,
                  transition: 'opacity 0.2s',
                }}>
                  <td style={{ padding: '14px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{
                        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                        background: u.role === 'admin' ? 'var(--c-accent)' : '#888',
                      }} />
                      <span style={{ fontWeight: 600, color: 'var(--c-text-1)', fontSize: 22 }}>
                        {u.username}
                      </span>
                      {u.username === me?.username && (
                        <span style={{
                          fontSize: 14, padding: '2px 7px', borderRadius: 4,
                          background: 'var(--c-accent-bg)', border: '1px solid var(--c-accent-border)',
                          color: 'var(--c-accent)', fontWeight: 600, letterSpacing: 1,
                        }}>คุณ</span>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    {u.username === me?.username ? (
                      <span style={{
                        fontSize: 16, padding: '4px 12px', borderRadius: 20, fontWeight: 600,
                        background: u.role === 'admin' ? 'rgba(99,179,237,0.12)' : 'rgba(160,160,160,0.12)',
                        color:      u.role === 'admin' ? '#63b3ed' : '#aaa',
                        border:     `1px solid ${u.role === 'admin' ? 'rgba(99,179,237,0.3)' : 'rgba(160,160,160,0.2)'}`,
                        letterSpacing: 1,
                      }}>
                        {u.role}
                      </span>
                    ) : (
                      <button
                        title="คลิกเพื่อสลับ role"
                        disabled={roleMut.isPending && roleMut.variables?.username === u.username}
                        onClick={() => roleMut.mutate({ username: u.username, role: u.role === 'admin' ? 'viewer' : 'admin' })}
                        style={{
                          fontSize: 16, padding: '4px 12px', borderRadius: 20, fontWeight: 600,
                          background: u.role === 'admin' ? 'rgba(99,179,237,0.12)' : 'rgba(160,160,160,0.12)',
                          color:      u.role === 'admin' ? '#63b3ed' : '#aaa',
                          border:     `1px solid ${u.role === 'admin' ? 'rgba(99,179,237,0.3)' : 'rgba(160,160,160,0.2)'}`,
                          letterSpacing: 1, cursor: 'pointer',
                          display: 'inline-flex', alignItems: 'center', gap: 5,
                          opacity: roleMut.isPending && roleMut.variables?.username === u.username ? 0.5 : 1,
                        }}
                        onMouseEnter={e => e.currentTarget.style.opacity = '0.7'}
                        onMouseLeave={e => e.currentTarget.style.opacity = roleMut.variables?.username === u.username ? '0.5' : '1'}
                      >
                        {u.role}
                        <svg viewBox="0 0 24 24" style={{ width: 11, height: 11, fill: 'none', stroke: 'currentColor', strokeWidth: 2.5, opacity: 0.6 }}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4"/>
                        </svg>
                      </button>
                    )}
                  </td>
                  <td style={{ padding: '18px 16px', fontSize: 20, color: 'var(--c-text-3)' }}>
                    {fmt(u.created_at)}
                  </td>
                  <td style={{ padding: '18px 16px', fontSize: 20, color: 'var(--c-text-3)' }}>
                    {fmt(u.last_login)}
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                      <button className={btnClass.warn}
                              onClick={() => setResetFor(u.username)}>
                        รีเซ็ต PW
                      </button>
                      {u.username !== me?.username && (
                        <button className={btnClass.danger}
                                onClick={() => setDeleteFor(u.username)}>
                          ลบ
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modals */}
      {showAdd && (
        <AddUserModal
          onClose={() => setShowAdd(false)}
          onSuccess={() => { qc.invalidateQueries({ queryKey: ['users'] }); showToast('เพิ่มผู้ใช้เรียบร้อย') }}
        />
      )}
      {resetFor && (
        <ResetPasswordModal
          username={resetFor}
          onClose={() => setResetFor(null)}
          onSuccess={() => showToast(`รีเซ็ต password "${resetFor}" เรียบร้อย`)}
        />
      )}
      {deleteFor && (
        <ConfirmModal
          title={`ลบผู้ใช้ "${deleteFor}"`}
          message="ผู้ใช้นี้จะถูกลบออกจากระบบถาวร ยืนยันหรือไม่?"
          confirmLabel="ลบผู้ใช้"
          danger
          onConfirm={() => { setDeleteFor(null); onDelete(deleteFor) }}
          onCancel={() => setDeleteFor(null)}
        />
      )}
    </div>
  )
}
