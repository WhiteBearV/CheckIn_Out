<template>
  <!--
    LivenessBadge.vue — Badge แสดงสถานะ Liveness
    ────────────────────────────────────────────────
    Props:
      status — 'confirmed' | 'pending' | 'challenge' | 'failed'

    สี:
      confirmed  → เขียว  (gui-in)
      pending    → เหลือง (gui-out)
      challenge  → ม่วง   (purple-400)
      failed     → แดง    (gui-fail)
  -->
  <span
    class="inline-flex items-center gap-1 px-2 py-0.5
           rounded-md text-xs font-semibold whitespace-nowrap"
    :class="badgeClass"
  >
    <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="dotClass" />
    {{ label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'pending' },
})

const badgeClass = computed(() => {
  switch (props.status) {
    case 'confirmed': return 'bg-gui-in/15     text-gui-in'
    case 'challenge': return 'bg-purple-500/15 text-purple-400'
    case 'failed':    return 'bg-gui-fail/15   text-gui-fail'
    default:          return 'bg-gui-out/15    text-gui-out'   // pending
  }
})

const dotClass = computed(() => {
  switch (props.status) {
    case 'confirmed': return 'bg-gui-in'
    case 'challenge': return 'bg-purple-400'
    case 'failed':    return 'bg-gui-fail'
    default:          return 'bg-gui-out'
  }
})

const label = computed(() => {
  switch (props.status) {
    case 'confirmed': return 'ผ่าน ✓'
    case 'challenge': return 'Challenge'
    case 'failed':    return 'ล้มเหลว'
    default:          return 'กำลังตรวจ'
  }
})
</script>
