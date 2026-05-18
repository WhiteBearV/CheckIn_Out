import { authFetch } from './client'

export async function fetchAttendanceToday() {
  const r = await authFetch('/attendance/today')
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

export async function fetchPerson(perId) {
  if (!perId) return null
  try {
    const r = await authFetch(`/person/${encodeURIComponent(perId)}`, {
      signal: AbortSignal.timeout(5000),
    })
    if (!r.ok) return null
    return r.json()
  } catch {
    return null
  }
}
