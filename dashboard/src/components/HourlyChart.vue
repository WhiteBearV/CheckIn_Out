<template>
  <!--
    HourlyChart.vue — Bar Chart การลงเวลาตามชั่วโมง
    ──────────────────────────────────────────────────
    ใช้ Chart.js โดยตรง (ไม่ผ่าน wrapper เพื่อควบคุมได้เต็มที่)

    Props:
      hourly — Array<{ hour: 0-23, in: number, out: number }>  (จาก useAttendance)

    การแก้ไข:
      - เปลี่ยนสี: แก้ COLOR_IN / COLOR_OUT
      - เปลี่ยนความสูง: แก้ style height ของ <div> ครอบ canvas
      - เปลี่ยน chart type: แก้ type: 'bar' เป็น 'line'
  -->
  <div class="bg-gui-panel border border-gui-border rounded-xl p-4">

    <!-- Header -->
    <h2 class="font-semibold text-sm mb-4 flex items-center gap-2">
      <span class="text-gui-out text-base">▊</span>
      การลงเวลาตามชั่วโมง
    </h2>

    <!-- Canvas container — แก้ height ที่นี่เพื่อเปลี่ยนความสูง chart -->
    <div class="relative" style="height: 180px">
      <canvas ref="chartEl" />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import {
  Chart,
  BarController, BarElement,
  CategoryScale, LinearScale,
  Tooltip, Legend,
} from 'chart.js'

// Register เฉพาะ components ที่ใช้ (ลด bundle size)
Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend)

// ── Props ──────────────────────────────────────────────────────────
const props = defineProps({
  hourly: { type: Array, required: true },
})

// ── สี chart ── แก้ได้ที่นี่ ─────────────────────────────────────
const COLOR_IN       = 'rgba(0,   220,   0, 0.75)'
const COLOR_IN_EDGE  = 'rgba(0,   220,   0, 1   )'
const COLOR_OUT      = 'rgba(255, 215,   0, 0.75)'
const COLOR_OUT_EDGE = 'rgba(255, 215,   0, 1   )'

// ── Chart instance ─────────────────────────────────────────────────
const chartEl = ref(null)
let chart = null

function buildChart() {
  if (chart) chart.destroy()

  chart = new Chart(chartEl.value, {
    type: 'bar',
    data: {
      // label แกน X: ชั่วโมง "0:00" ถึง "23:00"
      labels: props.hourly.map(h => `${h.hour}:00`),
      datasets: [
        {
          label: 'Check-In',
          data:  props.hourly.map(h => h.in),
          backgroundColor: COLOR_IN,
          borderColor:     COLOR_IN_EDGE,
          borderWidth: 1,
          borderRadius: 3,
        },
        {
          label: 'Check-Out',
          data:  props.hourly.map(h => h.out),
          backgroundColor: COLOR_OUT,
          borderColor:     COLOR_OUT_EDGE,
          borderWidth: 1,
          borderRadius: 3,
        },
      ],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },

      plugins: {
        legend: {
          labels: { color: '#7d8590', font: { size: 11 }, boxWidth: 12 },
        },
        tooltip: {
          backgroundColor: '#161b22',
          borderColor:     '#30363d',
          borderWidth:     1,
          titleColor:      '#e6edf3',
          bodyColor:       '#7d8590',
        },
      },

      scales: {
        x: {
          ticks: { color: '#7d8590', font: { size: 10 }, maxRotation: 0 },
          grid:  { color: 'rgba(48,54,61,0.3)' },
        },
        y: {
          beginAtZero: true,
          ticks: { color: '#7d8590', font: { size: 10 }, stepSize: 1 },
          grid:  { color: 'rgba(48,54,61,0.5)' },
        },
      },
    },
  })
}

// อัพเดตข้อมูลโดยไม่สร้าง chart ใหม่ (ประหยัด CPU)
function updateChart() {
  if (!chart) return
  chart.data.datasets[0].data = props.hourly.map(h => h.in)
  chart.data.datasets[1].data = props.hourly.map(h => h.out)
  chart.update('none')  // 'none' = ไม่มี animation เวลา update
}

// ── Lifecycle ──────────────────────────────────────────────────────
onMounted  (buildChart)
onUnmounted(() => chart?.destroy())

// watch hourly แล้ว update chart ทันที
watch(() => props.hourly, updateChart, { deep: true })
</script>
