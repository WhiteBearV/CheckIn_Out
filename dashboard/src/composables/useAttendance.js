// ─────────────────────────────────────────────────────────────────────
// composables/useAttendance.js — Shared-singleton composable
//
// State อยู่ระดับ module: ทุก component ที่เรียก useAttendance()
// แชร์ records / stats / persons ชุดเดียวกัน ไม่ reset เมื่อสลับ tab
// ─────────────────────────────────────────────────────────────────────

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchTodayAttendance } from '@/api/attendance.js'

const POLL_INTERVAL_MS = 10_000
const FEED_LIMIT       = 60

// ── Shared state (module-level) ────────────────────────────────────
const records   = ref([])
const loading   = ref(false)
const error     = ref(null)
const lastFetch = ref(null)

// ── Computed (module-level) ────────────────────────────────────────
const stats = computed(() => {
  const ins  = records.value.filter(r => r.status === 'IN')
  const outs = records.value.filter(r => r.status === 'OUT')

  // นับ "ยังอยู่" โดยดูจาก record ล่าสุดของแต่ละคน ไม่ใช่แค่มี OUT อยู่ใน set
  const latestStatus = {}
  for (const r of records.value) {
    const prev = latestStatus[r.per_id]
    if (!prev || r.check_time > prev.check_time) latestStatus[r.per_id] = r
  }
  const currentlyIn = Object.values(latestStatus).filter(r => r.status === 'IN').length

  return {
    totalIn:     ins.length,
    totalOut:    outs.length,
    total:       records.value.length,
    currentlyIn,
  }
})

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

const feed = computed(() =>
  [...records.value]
    .sort((a, b) => new Date(b.check_time) - new Date(a.check_time))
    .slice(0, FEED_LIMIT)
)

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
    if (r.status === 'IN') {
      if (!map[r.per_id].in_time ||
          new Date(r.check_time) < new Date(map[r.per_id].in_time))
        map[r.per_id].in_time = r.check_time
    }
    if (r.status === 'OUT') {
      if (!map[r.per_id].out_time ||
          new Date(r.check_time) > new Date(map[r.per_id].out_time))
        map[r.per_id].out_time = r.check_time
    }
  })
  Object.values(map).forEach(p => { p.status = p.out_time ? 'OUT' : 'IN' })
  return Object.values(map).sort((a, b) => {
    if (a.status !== b.status) return a.status === 'IN' ? -1 : 1
    return new Date(b.in_time ?? 0) - new Date(a.in_time ?? 0)
  })
})

// ── Fetch ──────────────────────────────────────────────────────────
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

// ── Polling (ref-count: เริ่มเมื่อมี component แรก, หยุดเมื่อไม่มีเลย) ──
let _timer  = null
let _users  = 0

export function useAttendance() {
  onMounted(() => {
    _users++
    if (_users === 1) {
      refresh()
      _timer = setInterval(refresh, POLL_INTERVAL_MS)
    }
  })
  onUnmounted(() => {
    _users--
    if (_users === 0) {
      clearInterval(_timer)
      _timer = null
    }
  })
  return { records, loading, error, lastFetch, stats, byOrg, hourly, feed, persons, refresh }
}
