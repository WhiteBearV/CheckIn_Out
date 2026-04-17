<template>
  <header class="bg-gui-panel border-b border-gui-border px-5 py-3
                 flex items-center justify-between gap-4 shrink-0">

    <!-- ── ซ้าย: Logo + Title ── -->
    <div class="flex items-center gap-3">
      <div class="w-9 h-9 rounded-xl bg-gui-in/15 flex items-center
                  justify-center text-xl shrink-0">
        👁
      </div>
      <div class="leading-tight">
        <h1 class="text-sm font-semibold text-gui-text">Face Attendance</h1>
        <p class="text-xs text-gui-dim">Dashboard</p>
      </div>
    </div>

    <!-- ── ขวา: Theme picker + วันที่ + เวลา ── -->
    <div class="flex items-center gap-4 md:gap-6 text-sm">

      <!-- Theme picker -->
      <div class="flex items-center gap-1 bg-gui-bg rounded-lg p-0.5 border border-gui-border/60">
        <button
          v-for="opt in themeOptions"
          :key="opt.value"
          @click="setTheme(opt.value)"
          :title="opt.label"
          :class="theme === opt.value
            ? 'bg-gui-panel text-gui-text shadow-sm'
            : 'text-gui-dim hover:text-gui-text'"
          class="px-2 py-1 rounded-md text-xs transition-colors"
        >
          {{ opt.icon }}
        </button>
      </div>

      <!-- วันที่ (ซ่อนบนจอเล็ก) -->
      <div class="hidden sm:block text-right">
        <div class="text-xs text-gui-dim">วันที่</div>
        <div class="text-xs font-medium leading-tight">{{ dateStr }}</div>
      </div>

      <!-- เวลา real-time -->
      <div class="text-right">
        <div class="text-xs text-gui-dim">เวลา</div>
        <div class="font-mono text-base font-bold text-gui-in tabular-nums">
          {{ timeStr }}
        </div>
      </div>

    </div>
  </header>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useTheme } from '@/composables/useTheme.js'

const { theme, setTheme } = useTheme()

const themeOptions = [
  { value: 'light', icon: '☀', label: 'ธีมสว่าง'    },
  { value: 'dark',  icon: '🌙', label: 'ธีมมืด'      },
  { value: 'auto',  icon: '💻', label: 'ตามระบบ (Auto)' },
]

// ── นาฬิกา real-time ──────────────────────────────────────────────
const now = ref(new Date())
let clockTimer = null
onMounted  (() => { clockTimer = setInterval(() => { now.value = new Date() }, 1000) })
onUnmounted(() => clearInterval(clockTimer))

const dateStr = computed(() =>
  now.value.toLocaleDateString('th-TH', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'short',
  })
)
const timeStr = computed(() =>
  now.value.toLocaleTimeString('th-TH', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
)
</script>
