<template>
  <!--
    AppHeader.vue — แถบหัวสุด (Global)
    ─────────────────────────────────────
    แสดง: ไอคอน + ชื่อระบบ | วันที่ | เวลา real-time
    ใช้ร่วมกันทุกหน้า — ไม่ผูกกับข้อมูล attendance

    นาฬิกาอัพเดตทุก 1 วินาทีด้วย setInterval
  -->
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

    <!-- ── ขวา: วันที่ + เวลา ── -->
    <div class="flex items-center gap-4 md:gap-6 text-sm">

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
