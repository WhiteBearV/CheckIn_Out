/** Mask per_id 13 หลัก → '*********6666' (โชว์แค่ 4 ตัวท้าย)
 *  ใช้ทุกที่ที่ต้องแสดง PID — ป้องกันเลขบัตรประชาชน 13 หลักรั่วทางหน้าจอ */
export function maskPid(perId) {
  if (!perId) return ''
  const s = String(perId)
  if (s.length <= 4) return s
  return '*'.repeat(s.length - 4) + s.slice(-4)
}
