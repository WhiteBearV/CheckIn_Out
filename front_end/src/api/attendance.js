import axios from 'axios'

const api = axios.create({ baseURL: '' })

export async function fetchAttendanceToday() {
  const { data } = await api.get('/attendance/today')
  return data
}

/** ดึงข้อมูลพนักงาน (รวม per_picpath รูป) จาก External API ผ่าน backend proxy */
export async function fetchPerson(perId) {
  if (!perId) return null
  try {
    const { data } = await api.get(`/person/${encodeURIComponent(perId)}`, { timeout: 5000 })
    return data
  } catch {
    return null
  }
}
