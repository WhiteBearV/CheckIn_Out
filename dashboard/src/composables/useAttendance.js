// ─────────────────────────────────────────────────────────────────────
// composables/useAttendance.js — Composable หลัก จัดการข้อมูล attendance
//
// ใช้งาน:
//   const { stats, byOrg, hourly, feed, loading, error, lastFetch, refresh }
//     = useAttendance()
//
// หน้าที่:
//   - fetch ข้อมูลจาก API ตอน mount
//   - polling อัตโนมัติทุก POLL_INTERVAL_MS
//   - คำนวณ stats / byOrg / hourly / feed จากข้อมูลดิบ
//   - component ต่างๆ รับข้อมูลผ่าน props (ไม่ต้อง fetch เอง)
// ─────────────────────────────────────────────────────────────────────

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchTodayAttendance } from '@/api/attendance.js'

// ── ค่าคงที่ ── แก้ที่นี่เพื่อเปลี่ยนพฤติกรรม ─────────────────────
const POLL_INTERVAL_MS = 10_000   // refresh ทุก N มิลลิวินาที (default 10 วิ)
const FEED_LIMIT       = 60       // แสดงสูงสุด N รายการล่าสุดใน feed

export function useAttendance() {

  // ── Raw state ──────────────────────────────────────────────────────
  const records   = ref([])       // ข้อมูลดิบจาก GET /attendance/today
  const loading   = ref(false)    // true ขณะกำลัง fetch
  const error     = ref(null)     // error message string (null = ปกติ)
  const lastFetch = ref(null)     // Date object ของครั้งล่าสุดที่ fetch สำเร็จ

  // ── Computed: สถิติรวม ─────────────────────────────────────────────
  const stats = computed(() => {
    const ins  = records.value.filter(r => r.status === 'IN')
    const outs = records.value.filter(r => r.status === 'OUT')

    // คนที่ "ยังอยู่" = มี IN แต่ per_id นั้นไม่มี OUT วันนี้
    const outIds      = new Set(outs.map(r => r.per_id))
    const currentlyIn = ins.filter(r => !outIds.has(r.per_id)).length

    return {
      totalIn:     ins.length,       // จำนวนครั้งที่ check-in วันนี้
      totalOut:    outs.length,      // จำนวนครั้งที่ check-out วันนี้
      total:       records.value.length,
      currentlyIn,                   // คนที่ยังอยู่ในที่ทำงาน
    }
  })

  // ── Computed: แยกตามหน่วยงาน ──────────────────────────────────────
  // Return: Array<{ name: string, in: number, out: number, total: number }>
  // เรียงจาก total มากไปน้อย
  const byOrg = computed(() => {
    const map = {}
    records.value.forEach(r => {
      const key = r.organize_th || 'ไม่ระบุหน่วยงาน'
      if (!map[key]) map[key] = { name: key, in: 0, out: 0 }
      if (r.status === 'IN')  map[key].in++
      if (r.status === 'OUT') map[key].out++
    })
    return Object.values(map)
      .map(o => ({ ...o, total: o.in + o.out }))
      .sort((a, b) => b.total - a.total)
  })

  // ── Computed: กระจายตามชั่วโมง (0–23) ────────────────────────────
  // Return: Array<{ hour: number, in: number, out: number }>  ยาว 24 ตัว
  const hourly = computed(() => {
    const hours = Array.from({ length: 24 }, (_, h) => ({ hour: h, in: 0, out: 0 }))
    records.value.forEach(r => {
      if (!r.check_time) return
      const h = new Date(r.check_time).getHours()
      if (r.status === 'IN')  hours[h].in++
      if (r.status === 'OUT') hours[h].out++
    })
    return hours
  })

  // ── Computed: feed (เรียงใหม่สุดก่อน, จำกัด FEED_LIMIT แถว) ───────
  const feed = computed(() =>
    [...records.value]
      .sort((a, b) => new Date(b.check_time) - new Date(a.check_time))
      .slice(0, FEED_LIMIT)
  )

  // ── Computed: persons — รวม IN + OUT ต่อคน (เหมือน GUI panel) ────
  // Return: Array<{
  //   per_id, name, prename_th, per_name, per_surname,
  //   posname_th, organize_th,
  //   in_time, out_time,   ← ISO string (null ถ้าไม่มี)
  //   status               ← 'IN' | 'OUT'
  // }>
  // เรียง: คนที่ยังอยู่ (IN) ขึ้นก่อน → OUT ทีหลัง
  const persons = computed(() => {
    const map = {}

    records.value.forEach(r => {
      if (!r.per_id) return
      if (!map[r.per_id]) {
        map[r.per_id] = {
          per_id:      r.per_id,
          name:        r.name        || '',
          prename_th:  r.prename_th  || '',
          per_name:    r.per_name    || '',
          per_surname: r.per_surname || '',
          posname_th:  r.posname_th  || '',
          organize_th: r.organize_th || '',
          in_time:     null,
          out_time:    null,
          status:      'IN',
        }
      }
      // เก็บ IN time แรกสุด
      if (r.status === 'IN') {
        if (!map[r.per_id].in_time ||
            new Date(r.check_time) < new Date(map[r.per_id].in_time))
          map[r.per_id].in_time = r.check_time
      }
      // เก็บ OUT time ล่าสุด
      if (r.status === 'OUT') {
        if (!map[r.per_id].out_time ||
            new Date(r.check_time) > new Date(map[r.per_id].out_time))
          map[r.per_id].out_time = r.check_time
      }
    })

    Object.values(map).forEach(p => {
      p.status = p.out_time ? 'OUT' : 'IN'
    })

    return Object.values(map).sort((a, b) => {
      if (a.status !== b.status) return a.status === 'IN' ? -1 : 1
      return new Date(b.in_time ?? 0) - new Date(a.in_time ?? 0)
    })
  })

  // ── Action: fetch & refresh ────────────────────────────────────────
  async function refresh() {
    loading.value = true
    error.value   = null
    try {
      records.value   = await fetchTodayAttendance()
      lastFetch.value = new Date()
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  // ── Polling lifecycle ──────────────────────────────────────────────
  // เริ่ม fetch ทันทีเมื่อ component mount แล้ว polling ต่อเรื่อยๆ
  // หยุด polling อัตโนมัติเมื่อ component unmount (ป้องกัน memory leak)
  let timer = null
  onMounted(() => {
    refresh()
    timer = setInterval(refresh, POLL_INTERVAL_MS)
  })
  onUnmounted(() => clearInterval(timer))

  // ── Return ─────────────────────────────────────────────────────────
  return { records, loading, error, lastFetch, stats, byOrg, hourly, feed, persons, refresh }
}
