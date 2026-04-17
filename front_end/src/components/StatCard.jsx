const accentMap = {
  green:  '#22c55e',
  orange: '#f97316',
  blue:   '#0089ff',
  purple: '#a855f7',
}

export default function StatCard({ title, value, subtitle, color, icon }) {
  const accent = accentMap[color] || accentMap.blue

  return (
    <div
      className="rounded p-5 flex flex-col gap-4 relative overflow-hidden"
      style={{
        background: 'var(--c-bg-card)',
        border:     '1px solid var(--c-border)',
        transition: 'background 0.2s',
      }}
    >
      {/* Glow behind icon */}
      <div
        className="absolute top-0 right-0 w-32 h-32 pointer-events-none"
        style={{ background: `radial-gradient(circle at 80% 20%, ${accent}18 0%, transparent 65%)` }}
      />

      {/* Icon + label */}
      <div className="flex items-center justify-between relative z-10">
        <span className="font-mono text-[11px] uppercase tracking-widest"
          style={{ color: 'var(--c-accent)' }}>
          {title}
        </span>
        <div
          className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0"
          style={{
            background: `${accent}18`,
            color:      accent,
            border:     `1px solid ${accent}30`,
          }}
        >
          {icon && <span className="w-4 h-4 [&>svg]:w-4 [&>svg]:h-4">{icon}</span>}
        </div>
      </div>

      {/* Value */}
      <div className="relative z-10">
        <p className="font-mono text-4xl leading-none" style={{ color: 'var(--c-text)' }}>
          {value ?? <span style={{ color: 'var(--c-text-4)' }}>—</span>}
        </p>
        {subtitle && (
          <p className="text-xs mt-1.5" style={{ color: 'var(--c-text-3)' }}>{subtitle}</p>
        )}
      </div>
    </div>
  )
}
