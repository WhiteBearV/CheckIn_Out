import { useEffect } from 'react'

export default function ConfirmModal({ title, message, confirmLabel = 'ยืนยัน', cancelLabel = 'ยกเลิก', danger = false, onConfirm, onCancel }) {
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 99999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
    }} onClick={e => e.target === e.currentTarget && onCancel()}>
      <div style={{
        width: '100%', maxWidth: 380,
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border)',
        borderRadius: 16, padding: '28px 28px 24px',
        boxShadow: '0 20px 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.06)',
        display: 'flex', flexDirection: 'column', gap: 12,
      }}>
        <div style={{ fontSize: 34, fontWeight: 700, color: 'var(--c-text-1)' }}>{title}</div>
        {message && (
          <div style={{ fontSize: 28, color: 'var(--c-text-3)', lineHeight: 1.6 }}>{message}</div>
        )}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 8 }}>
          <button onClick={onCancel} className="btn btn-ghost">
            {cancelLabel}
          </button>
          <button onClick={onConfirm} className={`btn ${danger ? 'btn-stop' : 'btn-primary'}`}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
