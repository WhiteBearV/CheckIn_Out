import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import StatCard from '../components/StatCard'
import AttendanceTable from '../components/AttendanceTable'
import { fetchAttendanceToday } from '../api/attendance'

const REFRESH_INTERVAL = 30_000

function computeStats(records) {
  const inCount  = records.filter(r => r.status === 'IN').length
  const outCount = records.filter(r => r.status === 'OUT').length
  const perIds   = [...new Set(records.map(r => r.per_id))]
  const stillInside = perIds.filter(id => {
    const recs = records.filter(r => r.per_id === id)
    return recs.some(r => r.status === 'IN') && !recs.some(r => r.status === 'OUT')
  }).length
  return { inCount, outCount, stillInside, total: perIds.length }
}

export default function Dashboard() {
  const { data = [], isLoading, dataUpdatedAt } = useQuery({
    queryKey: ['attendance-today'],
    queryFn: fetchAttendanceToday,
    refetchInterval: REFRESH_INTERVAL,
  })

  const stats = useMemo(() => computeStats(data), [data])

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-white">Dashboard</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            {new Date().toLocaleDateString('th-TH', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          {lastUpdated ? `อัพเดตล่าสุด ${lastUpdated}` : 'กำลังโหลด...'}
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="เข้างาน (IN) วันนี้"
          value={isLoading ? null : stats.inCount}
          color="green"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
            </svg>
          }
        />
        <StatCard
          title="ออกงาน (OUT) วันนี้"
          value={isLoading ? null : stats.outCount}
          color="orange"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
          }
        />
        <StatCard
          title="ยังอยู่ในอาคาร"
          value={isLoading ? null : stats.stillInside}
          color="blue"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
          }
        />
        <StatCard
          title="พนักงานทั้งหมดวันนี้"
          value={isLoading ? null : stats.total}
          subtitle="คนที่มีการลงเวลา"
          color="purple"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          }
        />
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-700">
          <h2 className="font-semibold text-slate-800 dark:text-white">รายการลงเวลาวันนี้</h2>
          <span className="text-xs text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-700 px-2.5 py-1 rounded-full">
            {data.length} รายการ
          </span>
        </div>
        <AttendanceTable records={data} isLoading={isLoading} />
      </div>
    </div>
  )
}
