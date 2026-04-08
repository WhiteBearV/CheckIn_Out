// ─────────────────────────────────────────────────────────────────────
// api/attendance.js — ฟังก์ชัน fetch ข้อมูลจาก FastAPI backend
//
// BASE_URL:
//   - โหมด dev  → /api  (Vite proxy ส่งต่อไป localhost:8000)
//   - โหมด prod → ตั้งค่า VITE_API_BASE_URL ใน dashboard/.env
//                 เช่น  VITE_API_BASE_URL=http://192.168.1.x:8000
//
// ถ้าต้องการเปลี่ยน base URL: แก้ค่า VITE_API_BASE_URL ใน .env เท่านั้น
// ─────────────────────────────────────────────────────────────────────

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

// ── Internal helper ───────────────────────────────────────────────
async function apiFetch(path) {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json()
}

// ── Public API functions ──────────────────────────────────────────

/**
 * ดึงรายการลงเวลาวันนี้ทั้งหมด
 *
 * Response: Array<{
 *   id, per_id, name, prename_th, per_name, per_surname,
 *   posname_th, organize_th, organize_id,
 *   status,        // "IN" | "OUT"
 *   camera_name,
 *   check_time     // ISO 8601 string
 * }>
 */
export const fetchTodayAttendance = () =>
  apiFetch('/attendance/today')

/**
 * ดึงประวัติลงเวลาของพนักงานคนใดคนหนึ่ง
 *
 * @param {string}  perId      — รหัสพนักงาน
 * @param {string}  [startDate] — YYYY-MM-DD  (optional)
 * @param {string}  [endDate]   — YYYY-MM-DD  (optional)
 */
export function fetchPersonHistory(perId, startDate, endDate) {
  const params = new URLSearchParams()
  if (startDate) params.set('start_date', startDate)
  if (endDate)   params.set('end_date',   endDate)
  const qs = params.toString() ? `?${params}` : ''
  return apiFetch(`/attendance/${perId}${qs}`)
}
