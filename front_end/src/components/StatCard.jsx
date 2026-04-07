export default function StatCard({ title, value, subtitle, color, icon }) {
  const colorMap = {
    blue:   'bg-blue-500/10 text-blue-500 dark:bg-blue-500/20',
    green:  'bg-green-500/10 text-green-500 dark:bg-green-500/20',
    orange: 'bg-orange-500/10 text-orange-500 dark:bg-orange-500/20',
    purple: 'bg-purple-500/10 text-purple-500 dark:bg-purple-500/20',
  }

  return (
    <div className="
      bg-white dark:bg-slate-800
      rounded-xl p-5
      border border-slate-200 dark:border-slate-700
      flex items-center gap-4
    ">
      <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 ${colorMap[color] || colorMap.blue}`}>
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide truncate">
          {title}
        </p>
        <p className="text-3xl font-bold text-slate-800 dark:text-white mt-0.5 leading-none">
          {value ?? '—'}
        </p>
        {subtitle && (
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{subtitle}</p>
        )}
      </div>
    </div>
  )
}
