import axios from 'axios'

const api = axios.create({ baseURL: '' })

export async function fetchAttendanceToday() {
  const { data } = await api.get('/attendance/today')
  return data
}
