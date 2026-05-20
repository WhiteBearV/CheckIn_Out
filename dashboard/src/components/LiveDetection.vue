<template>
  <section v-if="showSection">

    <!-- ── Header ── -->
    <div class="flex items-center justify-between mb-3">
      <h2 class="font-semibold text-sm flex items-center gap-2">
        <span
          class="inline-flex items-center gap-1.5 px-2 py-0.5
                 rounded-md text-xs font-bold"
          :class="cctv_mode
            ? 'bg-gui-out/15 text-gui-out'
            : active && !stale
              ? 'bg-gui-in/15 text-gui-in'
              : 'bg-gui-dim/15 text-gui-dim'"
        >
          <span
            class="w-1.5 h-1.5 rounded-full shrink-0"
            :class="cctv_mode ? 'bg-gui-out' : active && !stale ? 'bg-gui-in animate-pulse' : 'bg-gui-dim'"
          />
          {{ cctv_mode ? 'LAST' : 'LIVE' }}
        </span>
        {{ cctv_mode ? 'บันทึกรอบสุดท้าย' : 'ตรวจพบในกล้อง' }}
        <span class="text-xs text-gui-dim font-normal">({{ displayPersons.length }} คน)</span>
      </h2>

      <div class="text-xs text-gui-dim flex items-center gap-2">
        <span v-if="stale" class="text-gui-fail">● offline</span>
        <span v-else-if="cctv_mode" class="text-gui-out">● โหมด CCTV</span>
        <span v-else class="text-gui-in">● กำลังทำงาน</span>
        <span v-if="lastUpdateStr">{{ lastUpdateStr }}</span>
      </div>
    </div>

    <!-- ── List ── -->
    <div class="flex flex-col divide-y divide-gui-border/30">
      <div
        v-for="p in displayPersons"
        :key="p.per_id"
        class="flex items-center gap-3 py-2.5 relative"
      >
        <!-- แถบสีซ้าย -->
        <div class="absolute left-0 inset-y-0 w-[3px] rounded-r-sm"
          :class="livenessBorderClass(p.liveness)" />

        <!-- Avatar (รูปจาก API → fallback เป็นตัวอักษร) -->
        <div class="w-9 h-9 rounded-full overflow-hidden shrink-0 ml-1.5 border border-gui-border/40 flex items-center justify-center"
             :class="faceErrors[p.per_id] ? livenessAvatarClass(p.liveness) : 'bg-black/20'">
          <img
            v-if="!faceErrors[p.per_id]"
            :src="`${API_BASE}/person-profile/${p.per_id}`"
            class="w-full h-full object-cover"
            :alt="(p.per_name || p.display_name || '?')[0]"
            @error="faceErrors[p.per_id] = true"
          />
          <span v-else class="font-bold text-sm">
            {{ (p.per_name || p.display_name || '?')[0] }}
          </span>
        </div>

        <!-- ชื่อ + หน่วยงาน + liveness msg -->
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium text-gui-text truncate leading-snug">
            {{ p.display_name || p.per_id }}
          </div>
          <div class="text-[11px] text-gui-dim truncate leading-snug">
            {{ p.organize_th || p.posname_th || ' ' }}
          </div>
          <div
            v-if="!cctv_mode && p.liveness_msg"
            class="text-[11px] truncate leading-snug mt-0.5"
            :class="livenessMsgClass(p.liveness)"
          >
            {{ p.liveness_msg }}
          </div>
        </div>

        <!-- ขวา: badge + เวลาเข้า/ออก -->
        <div class="text-right shrink-0 flex flex-col items-end gap-1">
          <LivenessBadge v-if="!cctv_mode" :status="p.liveness" />
          <span v-else class="text-[10px] font-bold px-1.5 py-0.5 rounded"
                :class="p.checked_out ? 'bg-gui-out/15 text-gui-out' : 'bg-gui-in/15 text-gui-in'">
            {{ p.checked_out ? 'OUT' : 'IN' }}
          </span>
          <div
            v-if="p.checked_in && p.first_seen"
            class="text-[10px] font-mono text-gui-in/70 tabular-nums"
          >
            เข้า {{ formatTime(p.first_seen) }}
          </div>
          <div
            v-if="cctv_mode && p.checked_out && p.out_time"
            class="text-[10px] font-mono text-gui-out/70 tabular-nums"
          >
            ออก {{ formatTime(p.out_time) }}
          </div>
        </div>
      </div>
    </div>

  </section>
</template>

<script setup>
import { computed, ref, reactive, onUnmounted } from 'vue'
import LivenessBadge from './LivenessBadge.vue'
import { useLiveSession } from '@/composables/useLiveSession.js'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

// ── Photo error tracking (per per_id) ────────────────────────────
const faceErrors = reactive({})

const { active, stale, cctv_mode, persons, lastUpdate } = useLiveSession()

// face mode: เฉพาะคนที่อยู่ในกล้องตอนนี้ (in_frame=true จาก main.py)
const inFramePersons = computed(() => persons.value.filter(p => p.in_frame))

// cctv mode: แสดงทุกคนที่ check-in แล้วในรอบสุดท้าย
const lastSessionPersons = computed(() => persons.value.filter(p => p.checked_in))

// ใช้ list ตาม mode ปัจจุบัน
const displayPersons = computed(() =>
  cctv_mode.value ? lastSessionPersons.value : inFramePersons.value
)

// แสดง section เมื่อ: ไม่ stale และมีคนแสดง (face mode หรือ cctv mode)
const showSection = computed(() =>
  !stale.value && displayPersons.value.length > 0
)

const now = ref(new Date())
const _clockTimer = setInterval(() => { now.value = new Date() }, 3000)
onUnmounted(() => clearInterval(_clockTimer))

const lastUpdateStr = computed(() => {
  if (!lastUpdate.value) return ''
  const diff = Math.floor((now.value - lastUpdate.value) / 1000)
  if (diff < 60) return `${diff}s`
  return `${Math.floor(diff / 60)}m`
})

function livenessBorderClass(liveness) {
  switch (liveness) {
    case 'confirmed': return 'bg-gui-in'
    case 'challenge': return 'bg-purple-400'
    case 'failed':    return 'bg-gui-fail'
    default:          return 'bg-gui-out'
  }
}

function livenessAvatarClass(liveness) {
  switch (liveness) {
    case 'confirmed': return 'bg-gui-in/20 text-gui-in'
    case 'challenge': return 'bg-purple-500/20 text-purple-400'
    case 'failed':    return 'bg-gui-fail/20 text-gui-fail'
    default:          return 'bg-gui-out/20 text-gui-out'
  }
}

function livenessMsgClass(liveness) {
  switch (liveness) {
    case 'confirmed': return 'text-gui-in'
    case 'challenge': return 'text-purple-400'
    case 'failed':    return 'text-gui-fail'
    default:          return 'text-gui-out'
  }
}

function formatTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('th-TH', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
</script>
