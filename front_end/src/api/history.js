import axios from 'axios'

const api = axios.create({ baseURL: '' })

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
  const { data } = await api.get(`/api/history?${_qs(filters)}`)
  return data
}

export async function fetchHistoryFilters() {
  const { data } = await api.get('/api/history/filters')
  return data
}

export async function fetchReportSummary(filters) {
  const { data } = await api.get(`/api/report/summary?${_qs(filters)}`)
  return data
}

export function reportExportUrl(format, filters) {
  const qs = _qs(filters)
  return `/api/report/export?format=${format}${qs ? '&' + qs : ''}`
}
