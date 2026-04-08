<template>
  <!--
    StatCard.vue — Card แสดงตัวเลขสถิติ 1 ค่า
    ────────────────────────────────────────────
    Props:
      label    — ชื่อที่แสดงใต้ตัวเลข
      value    — ตัวเลข / ข้อความที่แสดง
      icon     — emoji หรือตัวอักษร
      color    — 'green' | 'yellow' | 'red' | 'blue'
      subLabel — ข้อความเล็กๆ เพิ่มเติม (optional)

    เพิ่มสีใหม่: เพิ่ม entry ใน colorMap ด้านล่าง
  -->
  <div
    class="bg-gui-panel border border-gui-border rounded-xl p-4
           flex items-center gap-4 transition-colors"
    :class="scheme.border"
  >
    <!-- ── ไอคอน ── -->
    <div
      class="w-12 h-12 rounded-xl flex items-center justify-center
             text-2xl shrink-0"
      :class="scheme.iconBg"
    >
      {{ icon }}
    </div>

    <!-- ── ข้อความ ── -->
    <div class="min-w-0">
      <!-- ตัวเลขใหญ่ -->
      <div
        class="text-3xl font-bold tabular-nums leading-none"
        :class="scheme.value"
      >
        {{ value }}
      </div>
      <!-- label -->
      <div class="text-sm text-gui-dim mt-1 truncate">{{ label }}</div>
      <!-- subLabel เล็ก (optional) -->
      <div v-if="subLabel" class="text-xs text-gui-dim/60 truncate">
        {{ subLabel }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

// ── Props ──────────────────────────────────────────────────────────
const props = defineProps({
  label:    { type: String,           required: true },
  value:    { type: [Number, String], required: true },
  icon:     { type: String,           default: '📊' },
  color:    { type: String,           default: 'blue' },
  subLabel: { type: String,           default: '' },
})

// ── สี mapping ─────────────────────────────────────────────────────
// เพิ่มธีมสีใหม่ได้ที่นี่
const colorMap = {
  green:  {
    border:  'hover:border-gui-in/50',
    iconBg:  'bg-gui-in/10  text-gui-in',
    value:   'text-gui-in',
  },
  yellow: {
    border:  'hover:border-gui-out/50',
    iconBg:  'bg-gui-out/10 text-gui-out',
    value:   'text-gui-out',
  },
  red:    {
    border:  'hover:border-gui-fail/50',
    iconBg:  'bg-gui-fail/10 text-gui-fail',
    value:   'text-gui-fail',
  },
  blue:   {
    border:  'hover:border-blue-500/50',
    iconBg:  'bg-blue-500/10 text-blue-400',
    value:   'text-blue-400',
  },
}

const scheme = computed(() => colorMap[props.color] ?? colorMap.blue)
</script>
