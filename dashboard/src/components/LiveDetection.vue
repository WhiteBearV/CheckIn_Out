<template>
  <section v-if="!stale && inFramePersons.length > 0">

    <!-- ── Header ── -->
    <div class="flex items-center justify-between mb-3">
      <h2 class="font-semibold text-sm flex items-center gap-2">
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
        <span class="text-xs text-gui-dim font-normal">({{ inFramePersons.length }} คน)</span>
      </h2>

      <div class="text-xs text-gui-dim flex items-center gap-2">
        <span v-if="stale" class="text-gui-fail">● offline</span>
        <span v-else class="text-gui-in">● กำลังทำงาน</span>
        <span v-if="lastUpdateStr">{{ lastUpdateStr }}</span>
      </div>
    </div>

    <!-- ── List ── -->
    <div class="flex flex-col divide-y divide-gui-border/30">
      <div
        v-for="p in inFramePersons"
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
            v-if="p.liveness_msg"
            class="text-[11px] truncate leading-snug mt-0.5"
            :class="livenessMsgClass(p.liveness)"
          >
            {{ p.liveness_msg }}
          </div>
        </div>

        <!-- ขวา: badge + เวลาเข้า (เฉพาะ confirmed เท่านั้น) -->
        <div class="text-right shrink-0 flex flex-col items-end gap-1">
          <LivenessBadge :status="p.liveness" />
          <div
            v-if="p.checked_in && p.first_seen"
            class="text-[10px] font-mono text-gui-in/70 tabular-nums"
          >
            {{ formatTime(p.first_seen) }}
          </div>
        </div>
      </div>
    </div>

  </section>
</template>

<script setup>
import { computed, ref, reactive } from 'vue'
import LivenessBadge from './LivenessBadge.vue'
import { useLiveSession } from '@/composables/useLiveSession.js'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

// ── Photo error tracking (per per_id) ────────────────────────────
const faceErrors = reactive({})

const { active, stale, persons, lastUpdate } = useLiveSession()

// เฉพาะคนที่อยู่ในกล้องตอนนี้ (in_frame=true จาก main.py)
const inFramePersons = computed(() => persons.value.filter(p => p.in_frame))

const now = ref(new Date())
setInterval(() => { now.value = new Date() }, 3000)

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
