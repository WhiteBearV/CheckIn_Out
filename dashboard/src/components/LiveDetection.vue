<template>
  <!--
    LiveDetection.vue — แสดงสถานะ real-time จาก main.py (เหมือน GUI panel)
    ══════════════════════════════════════════════════════════════════════════
    ข้อมูลจาก live_state.json ที่ main.py เขียนทุก 1 วินาที
    polling ทุก 2 วินาทีผ่าน useLiveSession composable

    Layout:
      [Header: LIVE badge + สถานะ main.py]
      ─────────────────────────────────────
      ถ้า main.py ไม่ได้รัน: Offline banner
      ถ้าไม่มีคนในกล้อง:    Empty state
      ถ้ามีคน:              Card grid แสดงแต่ละคน

    Liveness states:
      confirmed  → เขียว  — ผ่านการตรวจสอบ
      pending    → เหลือง — กำลังตรวจสอบ
      challenge  → ม่วง   — ระหว่าง finger challenge
      failed     → แดง    — ล้มเหลว
    ══════════════════════════════════════════════════════════════════════════
  -->
  <!-- แสดงเฉพาะเมื่อ main.py กำลังรันและตรวจพบใบหน้าจริงๆ -->
  <section v-if="!stale && persons.length > 0">

    <!-- ── Header ── -->
    <div class="flex items-center justify-between mb-3">
      <h2 class="font-semibold text-sm flex items-center gap-2">
        <!-- LIVE badge — กระพริบเฉพาะเมื่อ main.py กำลังรัน -->
        <span
          class="inline-flex items-center gap-1.5 px-2 py-0.5
                 rounded-md text-xs font-bold"
          :class="active && !stale
            ? 'bg-gui-in/15 text-gui-in'
            : 'bg-gui-dim/15 text-gui-dim'"
        >
          <span
            class="w-1.5 h-1.5 rounded-full shrink-0"
            :class="active && !stale ? 'bg-gui-in animate-pulse' : 'bg-gui-dim'"
          />
          LIVE
        </span>
        ตรวจพบในกล้อง
        <span class="text-xs text-gui-dim font-normal">
          ({{ persons.length }} คน)
        </span>
      </h2>

      <!-- สถานะ main.py + เวลาอัพเดต -->
      <div class="text-xs text-gui-dim flex items-center gap-2">
        <span v-if="stale" class="text-gui-fail">● main.py offline</span>
        <span v-else class="text-gui-in">● กำลังทำงาน</span>
        <span v-if="lastUpdateStr">{{ lastUpdateStr }}</span>
      </div>
    </div>

    <!-- ── Card Grid ── -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
      <div
        v-for="p in persons"
        :key="p.per_id"
        class="bg-gui-panel border rounded-xl p-3 flex flex-col gap-2
               transition-all"
        :class="livenessCardClass(p.liveness)"
      >
        <!-- ── ชื่อ + liveness badge ── -->
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <!-- ชื่อ -->
            <div class="font-semibold text-sm leading-tight truncate text-gui-text">
              {{ p.display_name || p.per_id }}
            </div>
            <!-- หน่วยงาน -->
            <div class="text-xs text-gui-dim truncate mt-0.5">
              {{ p.organize_th || '—' }}
            </div>
          </div>

          <!-- Liveness badge -->
          <LivenessBadge :status="p.liveness" class="shrink-0" />
        </div>

        <!-- ── ข้อความสถานะ liveness ── -->
        <div
          class="text-xs px-2 py-1 rounded-md leading-tight"
          :class="livenessMsgClass(p.liveness)"
        >
          {{ p.liveness_msg || '...' }}
        </div>

        <!-- ── เวลา first_seen / last_seen ── -->
        <div class="grid grid-cols-2 gap-1 text-xs text-gui-dim">
          <div>
            <div class="mb-0.5">เห็นครั้งแรก</div>
            <div class="font-mono tabular-nums text-gui-text/70">
              {{ formatTime(p.first_seen) }}
            </div>
          </div>
          <div>
            <div class="mb-0.5">ล่าสุด</div>
            <div class="font-mono tabular-nums text-gui-text/70">
              {{ formatTime(p.last_seen) }}
            </div>
          </div>
        </div>

        <!-- ── check-in / check-out indicator ── -->
        <div class="flex items-center gap-2 text-xs flex-wrap">
          <span
            v-if="p.checked_in"
            class="px-1.5 py-0.5 rounded bg-gui-in/15 text-gui-in font-semibold"
          >✓ เช็คอินแล้ว</span>
          <span
            v-if="p.checked_out"
            class="px-1.5 py-0.5 rounded bg-gui-out/15 text-gui-out font-semibold"
          >✓ เช็คเอาท์แล้ว</span>
          <span
            v-if="!p.checked_in && !p.checked_out"
            class="text-gui-dim"
          >ยังไม่ได้บันทึก</span>
        </div>

      </div>
    </div>

  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import LivenessBadge from './LivenessBadge.vue'
import { useLiveSession } from '@/composables/useLiveSession.js'

const { active, stale, persons, lastUpdate } = useLiveSession()

// ── แปลง lastUpdate → "Xs ที่แล้ว" ─────────────────────────────────
const now = ref(new Date())
setInterval(() => { now.value = new Date() }, 3000)

const lastUpdateStr = computed(() => {
  if (!lastUpdate.value) return ''
  const diff = Math.floor((now.value - lastUpdate.value) / 1000)
  if (diff < 60) return `${diff}s`
  return `${Math.floor(diff / 60)}m`
})

// ── สีของ card border ตาม liveness state ────────────────────────────
function livenessCardClass(liveness) {
  switch (liveness) {
    case 'confirmed':  return 'border-gui-in/40'
    case 'challenge':  return 'border-purple-500/40'
    case 'failed':     return 'border-gui-fail/40'
    default:           return 'border-gui-out/30'   // pending
  }
}

// ── สีของ message box ────────────────────────────────────────────────
function livenessMsgClass(liveness) {
  switch (liveness) {
    case 'confirmed':  return 'bg-gui-in/10   text-gui-in'
    case 'challenge':  return 'bg-purple-500/10 text-purple-400'
    case 'failed':     return 'bg-gui-fail/10  text-gui-fail'
    default:           return 'bg-gui-out/10   text-gui-out'   // pending
  }
}

// ── Format timestamp → HH:MM:SS ──────────────────────────────────────
function formatTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('th-TH', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
</script>
