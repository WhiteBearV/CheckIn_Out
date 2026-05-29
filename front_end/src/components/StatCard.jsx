export default function StatCard({ title, value, subtitle, delta, color, icon }) {
  const c = color || '#0089ff'
  return (
    <div className="stat" style={{
      '--glow-color':  c + '36',
      '--chip-bg':     c + '1f',
      '--chip-fg':     c,
      '--chip-border': c + '40',
    }}>
      <div className="glow" />
      <div className="chip">
        {icon && <span style={{ display: 'contents' }}>{icon}</span>}
      </div>
      <div className="body">
        <div className="eye">{title}</div>
        <div className="val">{value ?? <span style={{ color: 'var(--c-text-4)' }}>—</span>}</div>
        {subtitle && <div className="sub">{subtitle}</div>}
        {delta    && <div className="delta">{delta}</div>}
      </div>
    </div>
  )
}
