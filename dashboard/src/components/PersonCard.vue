<template>
  <!--
    PersonCard.vue — Card แสดงข้อมูลพนักงาน 1 คน
    ══════════════════════════════════════════════════════════════
    เทียบกับ GUI Panel:
      GUI: รูป snapshot | ชื่อ | PID | Dept | IN time | Last seen
      Web: รูป/avatar   | ชื่อ | PID | ตำแหน่ง/หน่วยงาน | IN | OUT | status badge

    Props:
      person — object จาก useAttendance.persons
               { per_id, name, per_name, per_surname, prename_th,
                 posname_th, organize_th, in_time, out_time, status }
      apiBase — BASE_URL สำหรับ photo endpoint (default '/api')

    ── สี border ──
      IN  (ยังอยู่)  → เขียว  (gui-in)
      OUT (ออกแล้ว) → เหลือง (gui-out)
  ══════════════════════════════════════════════════════════════
  -->
  <div
    class="bg-gui-panel border rounded-xl overflow-hidden
           flex flex-col transition-all hover:scale-[1.01]"
    :class="person.status === 'IN'
      ? 'border-gui-in/40'
      : person.status === 'PENDING'
      ? 'border-purple-500/40'
      : 'border-gui-out/30'"
  >
    <!-- ── ส่วนบน: รูป + status badge ── -->
    <div class="relative bg-black/30 aspect-video overflow-hidden flex items-center justify-center">

      <!-- รูป snapshot (โหลดจาก /api/person-photo/{per_id}) -->
      <img
        v-if="!photoError"
        :src="photoUrl"
        :alt="displayName"
        class="w-full h-full object-cover object-top cursor-zoom-in"
        @error="photoError = true"
        @click="lightboxOpen = true"
      />

      <!-- ไม่มีรูป: แสดง initial letter avatar -->
      <div v-else class="w-full h-full bg-gui-bg/60 flex items-center justify-center">
        <span class="text-6xl font-bold select-none opacity-30"
          :class="person.status === 'IN' ? 'text-gui-in'
                : person.status === 'PENDING' ? 'text-purple-400'
                : 'text-gui-out'">
          {{ initial }}
        </span>
      </div>

      <!-- Badge มุมบนขวา: PENDING → รอตรวจสอบ, IN/OUT → LivenessBadge หรือ StatusBadge -->
      <div class="absolute top-2 right-2">
        <span
          v-if="person.status === 'PENDING'"
          class="inline-flex items-center gap-1 px-2 py-0.5
                 rounded-md text-xs font-semibold
                 bg-gui-dim/15 text-gui-dim"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-gui-dim animate-pulse" />
          รอตรวจสอบ
        </span>
        <LivenessBadge v-else-if="person.liveness" :status="person.liveness" />
        <StatusBadge v-else :status="person.status" />
      </div>
    </div>

    <!-- ── Lightbox Modal ── -->
    <Teleport to="body">
      <Transition name="lb">
        <div
          v-if="lightboxOpen"
          class="fixed inset-0 z-50 flex flex-col items-center justify-center
                 bg-black/85 backdrop-blur-sm"
          @click.self="lightboxOpen = false"
          @keydown.esc.window="lightboxOpen = false"
        >
          <!-- รูปเต็ม -->
          <img
            :src="photoUrl"
            :alt="displayName"
            class="max-w-[90vw] max-h-[80vh] object-contain rounded-xl shadow-2xl"
          />
          <!-- ชื่อ + ปุ่มปิด -->
          <div class="mt-4 flex items-center gap-4">
            <span class="text-white font-semibold text-sm">{{ displayName }}</span>
            <button
              @click="lightboxOpen = false"
              class="px-3 py-1 rounded-lg text-xs border border-white/20
                     text-white/70 hover:text-white hover:border-white/50 transition-colors"
            >
              ✕ ปิด
            </button>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ── ส่วนล่าง: ข้อมูล ── -->
    <div class="p-3 flex flex-col gap-1.5 flex-1">

      <!-- ชื่อ (Thai) — ตัวเข้ม -->
      <div class="font-semibold text-sm leading-tight truncate text-gui-text">
        {{ displayName }}
      </div>

      <!-- ตำแหน่ง / หน่วยงาน -->
      <div class="text-xs text-gui-dim leading-relaxed">
        <div class="truncate">{{ person.posname_th  || '—' }}</div>
        <div class="truncate">{{ person.organize_th || '—' }}</div>
      </div>

      <!-- Liveness message (แสดงเมื่อ main.py กำลังประมวลผลคนนี้) -->
      <div
        v-if="person.liveness_msg && person.liveness"
        class="text-xs px-2 py-1 rounded-md leading-tight truncate"
        :class="livenessMsgClass"
      >
        {{ person.liveness_msg }}
      </div>

      <!-- PID — แสดง 4 ตัวท้าย + mask -->
      <div class="text-xs text-gui-dim/70 font-mono">
        ID: {{ maskedPid }}
      </div>

      <!-- เส้นคั่น -->
      <div class="border-t border-gui-border my-0.5" />

      <!-- เวลา IN / OUT ── เหมือน GUI panel -->
      <div class="grid grid-cols-2 gap-1 text-xs">
        <!-- IN time — แสดงเฉพาะ status=IN หรือ OUT (checked_in แล้ว) -->
        <div>
          <div class="text-gui-dim mb-0.5">เข้า (IN)</div>
          <div
            class="font-mono font-semibold tabular-nums"
            :class="person.status !== 'PENDING' && person.in_time ? 'text-gui-in' : 'text-gui-dim/40'"
          >
            {{ person.status !== 'PENDING' && person.in_time ? formatTime(person.in_time) : '—' }}
          </div>
        </div>
        <!-- OUT time -->
        <div>
          <div class="text-gui-dim mb-0.5">ออก (OUT)</div>
          <div
            class="font-mono font-semibold tabular-nums"
            :class="person.out_time ? 'text-gui-out' : 'text-gui-dim/40'"
          >
            {{ person.out_time ? formatTime(person.out_time) : '—' }}
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import StatusBadge   from './StatusBadge.vue'
import LivenessBadge from './LivenessBadge.vue'

// ── Props + Emits ──────────────────────────────────────────────────
const props = defineProps({
  person:    { type: Object,  required: true },
  apiBase:   { type: String,  default: '/api' },
  photoMode: { type: String,  default: 'profile' }, // 'profile' | 'verify'
})

const emit = defineEmits(['checked-out'])

// ── Lightbox ───────────────────────────────────────────────────────
const lightboxOpen = ref(false)

// ── Checkout ───────────────────────────────────────────────────────
const checkingOut = ref(false)

async function doCheckout() {
  if (checkingOut.value) return
  checkingOut.value = true
  try {
    const res  = await fetch(`${props.apiBase}/attendance/checkout/${props.person.per_id}`, { method: 'POST' })
    const data = await res.json()
    if (data.success) {
      emit('checked-out', props.person.per_id)
    } else {
      alert(data.reason || 'ไม่สามารถลงชื่อออกได้')
    }
  } catch {
    alert('เชื่อมต่อ API ไม่ได้')
  } finally {
    checkingOut.value = false
  }
}

// ── Photo ─────────────────────────────────────────────────────────
const photoError = ref(false)

const photoUrl = computed(() => {
  if (props.photoMode === 'verify') {
    // รูปจากกล้องตอน verify จริง (_IN.jpg หรือ _OUT.jpg)
    const st = props.person.status === 'OUT' ? 'OUT' : 'IN'
    return `${props.apiBase}/person-photo/${props.person.per_id}?status=${st}`
  }
  // default: รูปโปรไฟล์จาก External API (per_picpath) เท่านั้น
  return `${props.apiBase}/person-profile/${props.person.per_id}`
})

// ── Display name ───────────────────────────────────────────────────
const displayName = computed(() => {
  if (props.person.name) return props.person.name
  return [props.person.prename_th, props.person.per_name, props.person.per_surname]
    .filter(Boolean).join(' ') || props.person.per_id
})

// ตัวอักษรแรกสำหรับ avatar (ใช้ per_name ก่อน)
const initial = computed(() => {
  if (props.person.per_name)  return props.person.per_name[0]
  if (displayName.value)      return displayName.value.replace(/^[^\s]+\s/, '')[0] ?? '?'
  return '?'
})

// PID: แสดง xxx...xxxx (ซ่อนกลาง เผยแค่ 4 ตัวท้าย)
const maskedPid = computed(() => {
  const pid = String(props.person.per_id ?? '')
  if (pid.length <= 4) return pid
  return '•'.repeat(pid.length - 4) + pid.slice(-4)
})

// สีของ liveness message box — เหมือน LiveDetection.vue
const livenessMsgClass = computed(() => {
  switch (props.person.liveness) {
    case 'confirmed': return 'bg-gui-in/10   text-gui-in'
    case 'challenge': return 'bg-purple-500/10 text-purple-400'
    case 'failed':    return 'bg-gui-fail/10  text-gui-fail'
    default:          return 'bg-gui-out/10   text-gui-out'   // pending
  }
})

// ── Helpers ────────────────────────────────────────────────────────
function formatTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('th-TH', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
</script>

<style scoped>
.lb-enter-active, .lb-leave-active { transition: opacity 0.2s ease; }
.lb-enter-from,  .lb-leave-to     { opacity: 0; }
</style>
