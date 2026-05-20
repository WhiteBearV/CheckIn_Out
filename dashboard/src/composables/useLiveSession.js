// ─────────────────────────────────────────────────────────────────────
// composables/useLiveSession.js — Shared-singleton composable
//
// State อยู่ระดับ module: ทุก component ที่เรียก useLiveSession()
// แชร์ persons / stale ชุดเดียวกัน ไม่ reset เมื่อสลับ tab
// ─────────────────────────────────────────────────────────────────────

import { ref, onMounted, onUnmounted } from 'vue'
import { apiFetch } from '@/api/attendance.js'

const POLL_MS = 2_000

// ── Shared state (module-level) ────────────────────────────────────
const active     = ref(false)
const stale      = ref(true)
const cctv_mode  = ref(false)
const persons    = ref([])
const loading    = ref(false)
const error      = ref(null)
const lastUpdate = ref(null)

// ── Fetch ──────────────────────────────────────────────────────────
async function fetchLive() {
  loading.value = true
  try {
    const data = await apiFetch('/session/live')
    active.value     = data.active    ?? false
    stale.value      = data.stale     ?? true
    cctv_mode.value  = data.cctv_mode ?? false
    persons.value    = data.persons   ?? []
    lastUpdate.value = new Date()
    error.value      = null
  } catch (e) {
    error.value      = e.message
    active.value     = false
    stale.value      = true
    cctv_mode.value  = false
    // ไม่ clear persons เพื่อให้ last session ยังแสดงได้เมื่อ API มีปัญหาชั่วคราว
  } finally {
    loading.value = false
  }
}

// ── Polling (ref-count) ────────────────────────────────────────────
let _timer = null
let _users = 0

export function useLiveSession() {
  onMounted(() => {
    _users++
    if (_users === 1) {
      fetchLive()
      _timer = setInterval(fetchLive, POLL_MS)
    }
  })
  onUnmounted(() => {
    _users--
    if (_users === 0) {
      clearInterval(_timer)
      _timer = null
    }
  })
  return { active, stale, cctv_mode, persons, loading, error, lastUpdate }
}
