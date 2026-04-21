// ─────────────────────────────────────────────────────────────────────
// composables/useLiveSession.js — ดึงสถานะ real-time จาก main.py
//
// ใช้งาน:
//   const { active, stale, persons, loading, error, lastUpdate }
//     = useLiveSession()
//
// หน้าที่:
//   - polling GET /session/live ทุก POLL_MS มิลลิวินาที
//   - คืน persons พร้อม liveness status แบบ real-time
//   - ถ้า main.py ไม่ได้รัน: active=false, persons=[]
// ─────────────────────────────────────────────────────────────────────

import { ref, onMounted, onUnmounted } from 'vue'

const POLL_MS = 2_000   // polling interval (2 วินาที)
const API_URL = '/session/live'

export function useLiveSession() {

  // ── State ──────────────────────────────────────────────────────────
  const active     = ref(false)   // main.py กำลังรันอยู่
  const stale      = ref(true)    // ข้อมูลเก่าเกิน 5 วินาที (main.py หยุด?)
  const persons    = ref([])      // รายชื่อที่ตรวจพบ + liveness
  const loading    = ref(false)   // กำลัง fetch อยู่
  const error      = ref(null)    // error string (null = ปกติ)
  const lastUpdate = ref(null)    // Date ของครั้งล่าสุดที่ได้รับข้อมูล

  // ── Fetch ──────────────────────────────────────────────────────────
  async function fetchLive() {
    loading.value = true
    try {
      const res  = await fetch(API_URL)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()

      active.value     = data.active  ?? false
      stale.value      = data.stale   ?? true
      persons.value    = data.persons ?? []
      lastUpdate.value = new Date()
      error.value      = null
    } catch (e) {
      error.value   = e.message
      active.value  = false
      stale.value   = true
      persons.value = []
    } finally {
      loading.value = false
    }
  }

  // ── Polling lifecycle ──────────────────────────────────────────────
  let timer = null
  onMounted(() => {
    fetchLive()
    timer = setInterval(fetchLive, POLL_MS)
  })
  onUnmounted(() => clearInterval(timer))

  return { active, stale, persons, loading, error, lastUpdate }
}
