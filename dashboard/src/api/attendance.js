// api/attendance.js — ฟังก์ชัน fetch ข้อมูลจาก FastAPI backend
//
// BASE_URL:
//   - โหมด dev  → /api  (Vite proxy ส่งต่อไป localhost:8000)
//   - โหมด prod → ตั้งค่า VITE_API_BASE_URL ใน dashboard/.env
//                 เช่น  VITE_API_BASE_URL=http://192.168.1.x:8000

import { getToken, logout } from '@/composables/useAuth.js'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

// ── Internal helper ───────────────────────────────────────────────────────────

function authHeaders() {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function request(method, path, body) {
  const opts = {
    method,
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
  }
  if (body !== undefined) opts.body = JSON.stringify(body)

  const res = await fetch(`${BASE_URL}${path}`, opts)

  if (res.status === 401) {
    logout()
    window.location.href = '/#/login'
    throw new Error('Session หมดอายุ กรุณาเข้าสู่ระบบใหม่')
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `API ${res.status}: ${path}`)
  }
  return res.json()
}

export const apiFetch  = (path)        => request('GET',    path)
export const apiPost   = (path, body)  => request('POST',   path, body)
export const apiPut    = (path, body)  => request('PUT',    path, body)
export const apiPatch  = (path, body)  => request('PATCH',  path, body)
export const apiDelete = (path)        => request('DELETE', path)

// ── Stream URL helper (MJPEG ใช้ query param token) ──────────────────────────

export function streamUrl(path) {
  const t = getToken()
  const sep = path.includes('?') ? '&' : '?'
  return `${BASE_URL}${path}${t ? `${sep}token=${encodeURIComponent(t)}` : ''}`
}

// ── Public API functions ──────────────────────────────────────────────────────

export const fetchTodayAttendance = () =>
  apiFetch('/attendance/today')

export function fetchAttendanceRange(startDate, endDate) {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate })
  return apiFetch(`/attendance/range?${params}`)
}

export function fetchAttendanceByDate(date) {
  const qs = date ? `?date=${encodeURIComponent(date)}` : ''
  return apiFetch(`/attendance/by-date${qs}`)
}

export function fetchPersonHistory(perId, startDate, endDate) {
  const params = new URLSearchParams()
  if (startDate) params.set('start_date', startDate)
  if (endDate)   params.set('end_date',   endDate)
  const qs = params.toString() ? `?${params}` : ''
  return apiFetch(`/attendance/${perId}${qs}`)
}
