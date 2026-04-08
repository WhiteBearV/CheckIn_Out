<template>
  <!--
    StatusBadge.vue — Badge แสดงสถานะ IN / OUT
    ─────────────────────────────────────────────
    Props:
      status — 'IN' | 'OUT'

    สี:
      IN  → เขียว (gui-in  #00dc00)
      OUT → เหลือง (gui-out #ffd700)
  -->
  <span
    class="inline-flex items-center gap-1.5 px-2 py-0.5
           rounded-md text-xs font-semibold"
    :class="status === 'IN'
      ? 'bg-gui-in/15  text-gui-in'
      : 'bg-gui-out/15 text-gui-out'"
  >
    <!-- จุดสี -->
    <span
      class="w-1.5 h-1.5 rounded-full shrink-0"
      :class="status === 'IN' ? 'bg-gui-in' : 'bg-gui-out'"
    />
    {{ status }}
  </span>
</template>

<script setup>
defineProps({
  status: { type: String, required: true },   // 'IN' | 'OUT'
})
</script>
