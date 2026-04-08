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
    <div class="relative bg-black/30 aspect-video flex items-center justify-center">

      <!-- รูป snapshot (โหลดจาก /api/person-photo/{per_id}) -->
      <img
        v-if="!photoError"
        :src="photoUrl"
        :alt="displayName"
        class="w-full h-full object-cover"
        @error="photoError = true"
      />

      <!-- Fallback: วงกลม Avatar เมื่อไม่มีรูป -->
      <div
        v-else
        class="w-20 h-20 rounded-full flex items-center justify-center
               text-3xl font-bold"
        :class="person.status === 'IN'
          ? 'bg-gui-in/20 text-gui-in'
          : person.status === 'PENDING'
          ? 'bg-purple-500/20 text-purple-400'
          : 'bg-gui-out/20 text-gui-out'"
      >
        {{ initial }}
      </div>

      <!-- Badge มุมบนขวา: ถ้ามี liveness → แสดง LivenessBadge แทน StatusBadge -->
      <div class="absolute top-2 right-2">
        <LivenessBadge v-if="person.liveness" :status="person.liveness" />
        <StatusBadge
          v-else-if="person.status !== 'PENDING'"
          :status="person.status"
        />
        <span
          v-else
          class="inline-flex items-center gap-1 px-2 py-0.5
                 rounded-md text-xs font-semibold
                 bg-gui-dim/15 text-gui-dim"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-gui-dim" />
          รอตรวจ
        </span>
      </div>
    </div>

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
        <!-- IN time -->
        <div>
          <div class="text-gui-dim mb-0.5">เข้า (IN)</div>
          <div class="font-mono font-semibold text-gui-in tabular-nums">
            {{ formatTime(person.in_time) }}
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

// ── Props ──────────────────────────────────────────────────────────
const props = defineProps({
  person:  { type: Object, required: true },
  apiBase: { type: String, default: '/api' },
})

// ── Photo ─────────────────────────────────────────────────────────
const photoError = ref(false)

// URL ดึงรูปจาก endpoint (ถ้า 404 → photoError = true → แสดง avatar)
const photoUrl = computed(() =>
  `${props.apiBase}/person-photo/${props.person.per_id}`
)

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
