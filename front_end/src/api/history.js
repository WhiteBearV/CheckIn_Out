import { authFetch } from './client'

function _qs({ from, to, organize_id, per_id, camera_name }) {
  const p = new URLSearchParams()
  if (from)        p.set('from', from)
  if (to)          p.set('to',   to)
  if (organize_id) p.set('organize_id', organize_id)
  if (per_id)      p.set('per_id',      per_id)
  if (camera_name) p.set('camera_name', camera_name)
  return p.toString()
}

export async function fetchHistory(filters) {
  const r = await authFetch(`/api/history?${_qs(filters)}`)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function fetchHistoryFilters() {
  const r = await authFetch('/api/history/filters')
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function fetchReportSummary(filters) {
  const r = await authFetch(`/api/report/summary?${_qs(filters)}`)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export function reportExportUrl(format, filters) {
  const qs = _qs(filters)
  return `/api/report/export?format=${format}${qs ? '&' + qs : ''}`
}
