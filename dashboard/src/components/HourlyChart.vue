<template>
  <div class="bg-gui-panel border border-gui-border rounded-xl p-4">
    <h2 class="font-semibold text-sm mb-4 flex items-center gap-2">
      <span class="text-gui-out text-base">▊</span>
      การลงเวลาตามชั่วโมง
    </h2>
    <div class="relative" style="height: 180px">
      <canvas ref="chartEl" />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import {
  Chart,
  LineController, LineElement, PointElement,
  CategoryScale, LinearScale,
  Tooltip, Legend, Filler,
} from 'chart.js'
import { useTheme } from '@/composables/useTheme.js'

Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

const props = defineProps({
  hourly: { type: Array, required: true },
})

const { theme } = useTheme()

// อ่านสีจาก CSS variable ที่ตอบสนองต่อ theme
function getCssVar(name) {
  return `rgb(${getComputedStyle(document.documentElement).getPropertyValue(name).trim()})`
}

const COLOR_IN       = 'rgba(0,   220,   0, 1)'
const COLOR_IN_FILL  = 'rgba(0,   220,   0, 0.12)'
const COLOR_OUT      = 'rgba(255, 215,   0, 1)'
const COLOR_OUT_FILL = 'rgba(255, 215,   0, 0.08)'

const chartEl = ref(null)
let chart = null

function buildChart() {
  if (chart) chart.destroy()

  const colorPanel  = getCssVar('--gui-panel')
  const colorBorder = getCssVar('--gui-border')
  const colorText   = getCssVar('--gui-text')
  const colorDim    = getCssVar('--gui-dim')

  chart = new Chart(chartEl.value, {
    type: 'line',
    data: {
      labels: props.hourly.map(h => `${h.hour}:00`),
      datasets: [
        {
          label:                'Check-In',
          data:                 props.hourly.map(h => h.in),
          borderColor:          COLOR_IN,
          backgroundColor:      COLOR_IN_FILL,
          borderWidth:          2,
          pointRadius:          3,
          pointHoverRadius:     5,
          pointBackgroundColor: COLOR_IN,
          tension:              0.4,
          fill:                 true,
        },
        {
          label:                'Check-Out',
          data:                 props.hourly.map(h => h.out),
          borderColor:          COLOR_OUT,
          backgroundColor:      COLOR_OUT_FILL,
          borderWidth:          2,
          pointRadius:          3,
          pointHoverRadius:     5,
          pointBackgroundColor: COLOR_OUT,
          tension:              0.4,
          fill:                 true,
        },
      ],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },

      plugins: {
        legend: {
          labels: { color: colorDim, font: { size: 11 }, boxWidth: 12 },
        },
        tooltip: {
          backgroundColor: colorPanel,
          borderColor:     colorBorder,
          borderWidth:     1,
          titleColor:      colorText,
          bodyColor:       colorDim,
        },
      },

      scales: {
        x: {
          ticks: { color: colorDim, font: { size: 10 }, maxRotation: 0 },
          grid:  { color: `${colorBorder.replace('rgb', 'rgba').replace(')', ', 0.4)')}` },
        },
        y: {
          beginAtZero: true,
          ticks: { color: colorDim, font: { size: 10 }, stepSize: 1 },
          grid:  { color: `${colorBorder.replace('rgb', 'rgba').replace(')', ', 0.6)')}` },
        },
      },
    },
  })
}

function updateData() {
  if (!chart) return
  chart.data.datasets[0].data = props.hourly.map(h => h.in)
  chart.data.datasets[1].data = props.hourly.map(h => h.out)
  chart.update('none')
}

onMounted(buildChart)
onUnmounted(() => chart?.destroy())

// rebuild เมื่อ theme เปลี่ยน (สีต้องอ่านใหม่หลัง CSS variable อัพเดต)
watch(theme, () => {
  // รอ 1 tick ให้ CSS variable อัพเดตก่อน
  setTimeout(buildChart, 50)
})

watch(() => props.hourly, updateData, { deep: true })
</script>
