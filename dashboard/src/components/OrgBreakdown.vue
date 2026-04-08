<template>
  <!--
    OrgBreakdown.vue — สถิติแยกตามหน่วยงาน
    ─────────────────────────────────────────
    แสดง progress bar + ตัวเลข IN/OUT สำหรับแต่ละหน่วยงาน
    เรียงจาก total มากไปน้อย (จัดการใน useAttendance)

    Props:
      byOrg — Array<{ name, in, out, total }>  (จาก useAttendance)
  -->
  <div class="bg-gui-panel border border-gui-border rounded-xl
              flex flex-col h-full overflow-hidden">

    <!-- Header -->
    <div class="px-4 py-3 border-b border-gui-border shrink-0">
      <h2 class="font-semibold text-sm flex items-center gap-2">
        <span class="text-blue-400">▤</span>
        แยกตามหน่วยงาน
      </h2>
    </div>

    <!-- Empty state -->
    <div
      v-if="byOrg.length === 0"
      class="flex-1 flex flex-col items-center justify-center
             text-gui-dim text-sm gap-2"
    >
      <span class="text-3xl">🏢</span>
      ไม่มีข้อมูล
    </div>

    <!-- List -->
    <div v-else class="flex-1 overflow-auto p-3 space-y-2">
      <div
        v-for="org in byOrg"
        :key="org.name"
        class="p-3 rounded-lg bg-gui-border/10
               hover:bg-gui-border/20 transition-colors"
      >
        <!-- ชื่อหน่วยงาน + ตัวเลข IN / OUT -->
        <div class="flex items-center justify-between mb-2">
          <!-- ชื่อ: ตัดให้สั้นถ้ายาวเกิน -->
          <span class="text-xs font-medium truncate flex-1 mr-2">
            {{ org.name }}
          </span>
          <div class="flex items-center gap-2 shrink-0 text-xs font-semibold">
            <span class="text-gui-in">↑{{ org.in }}</span>
            <span class="text-gui-dim">/</span>
            <span class="text-gui-out">↓{{ org.out }}</span>
          </div>
        </div>

        <!-- Progress bar: สัดส่วนเทียบกับ org ที่มีคนมากสุด -->
        <div class="h-1.5 bg-gui-border rounded-full overflow-hidden">
          <div
            class="h-full bg-gui-in rounded-full transition-all duration-700"
            :style="{ width: barWidth(org.total) }"
          />
        </div>

        <!-- total -->
        <div class="text-right text-xs text-gui-dim mt-1">
          {{ org.total }} รายการ
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

// ── Props ──────────────────────────────────────────────────────────
const props = defineProps({
  byOrg: { type: Array, required: true },
})

// หา total สูงสุดเพื่อคำนวณ % progress bar
const maxTotal = computed(() =>
  Math.max(1, ...props.byOrg.map(o => o.total))
)

/** คืน width% สำหรับ progress bar ของ org นั้น */
function barWidth(total) {
  return `${(total / maxTotal.value) * 100}%`
}
</script>
