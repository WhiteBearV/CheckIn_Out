<template>
  <!--
    AttendanceFeed.vue — ตารางรายการลงเวลา (Live Feed)
    ────────────────────────────────────────────────────
    แสดงรายการล่าสุดก่อน, scroll ได้, responsive

    Props:
      feed    — Array ของ record (จาก useAttendance.feed)
      loading — boolean แสดง loading state
  -->
  <div class="bg-gui-panel border border-gui-border rounded-xl
              flex flex-col h-full overflow-hidden">

    <!-- ── Header ── -->
    <div class="px-4 py-3 border-b border-gui-border
                flex items-center justify-between shrink-0">
      <h2 class="font-semibold text-sm flex items-center gap-2">
        <!-- dot กระพริบ = live -->
        <span class="w-2 h-2 rounded-full bg-gui-in animate-pulse-slow" />
        รายการล่าสุด
      </h2>
      <span class="text-xs text-gui-dim bg-gui-border/30
                   px-2 py-0.5 rounded-full">
        {{ feed.length }} รายการ
      </span>
    </div>

    <!-- ── Loading (ยังไม่มีข้อมูล) ── -->
    <div
      v-if="loading && feed.length === 0"
      class="flex-1 flex items-center justify-center text-gui-dim text-sm"
    >
      <span class="animate-pulse">กำลังโหลด...</span>
    </div>

    <!-- ── Empty state ── -->
    <div
      v-else-if="feed.length === 0"
      class="flex-1 flex flex-col items-center justify-center
             text-gui-dim text-sm gap-2"
    >
      <span class="text-3xl">📋</span>
      ยังไม่มีการลงเวลาวันนี้
    </div>

    <!-- ── ตาราง ── -->
    <div v-else class="flex-1 overflow-auto">
      <table class="w-full text-sm">

        <!-- Table Header — sticky ไม่เลื่อนตาม scroll -->
        <thead class="sticky top-0 bg-gui-panel/95 backdrop-blur-sm z-10">
          <tr class="text-gui-dim text-xs border-b border-gui-border">
            <th class="px-4 py-2 text-left font-medium">ชื่อ — นามสกุล</th>
            <!-- คอลัมน์ตำแหน่ง/หน่วยงาน ซ่อนบนจอเล็ก -->
            <th class="px-4 py-2 text-left font-medium hidden md:table-cell">
              ตำแหน่ง / หน่วยงาน
            </th>
            <th class="px-4 py-2 text-center font-medium">สถานะ</th>
            <th class="px-4 py-2 text-right font-medium">เวลา</th>
          </tr>
        </thead>

        <tbody>
          <tr
            v-for="row in feed"
            :key="row.id"
            class="border-b border-gui-border/40
                   hover:bg-gui-border/10 transition-colors"
          >
            <!-- ── Avatar + ชื่อ ── -->
            <td class="px-4 py-2.5">
              <div class="flex items-center gap-2.5">
                <!-- วงกลม Avatar แสดงตัวอักษรแรกของชื่อ -->
                <div
                  class="w-7 h-7 rounded-full flex items-center justify-center
                         text-xs font-bold shrink-0"
                  :class="row.status === 'IN'
                    ? 'bg-gui-in/20  text-gui-in'
                    : 'bg-gui-out/20 text-gui-out'"
                >
                  {{ getInitial(row) }}
                </div>
                <div class="min-w-0">
                  <!-- ชื่อเต็ม -->
                  <div class="truncate font-medium text-gui-text">
                    {{ row.name || buildFullName(row) }}
                  </div>
                  <!-- หน่วยงาน (แสดงเฉพาะจอเล็ก) -->
                  <div class="text-xs text-gui-dim truncate md:hidden">
                    {{ row.organize_th || '—' }}
                  </div>
                </div>
              </div>
            </td>

            <!-- ── ตำแหน่ง / หน่วยงาน (จอใหญ่) ── -->
            <td class="px-4 py-2.5 hidden md:table-cell">
              <div class="text-xs text-gui-dim leading-relaxed">
                <div>{{ row.posname_th  || '—' }}</div>
                <div>{{ row.organize_th || '—' }}</div>
              </div>
            </td>

            <!-- ── Status badge ── -->
            <td class="px-4 py-2.5 text-center">
              <StatusBadge :status="row.status" />
            </td>

            <!-- ── เวลา ── -->
            <td class="px-4 py-2.5 text-right font-mono text-xs
                       text-gui-dim whitespace-nowrap">
              {{ formatTime(row.check_time) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import StatusBadge from './StatusBadge.vue'

// ── Props ──────────────────────────────────────────────────────────
defineProps({
  feed:    { type: Array,   required: true },
  loading: { type: Boolean, default: false },
})

// ── Helpers ────────────────────────────────────────────────────────

/** ดึงตัวอักษรแรกของชื่อ สำหรับ avatar */
function getInitial(row) {
  // ลอง per_name ก่อน ถ้าไม่มีค่อยดึงจาก name
  if (row.per_name) return row.per_name[0]
  if (row.name) {
    // ตัด prefix คำนำหน้า เช่น "ร้อยตรี วีรภัทร" → "ว"
    const parts = row.name.split(' ')
    return parts[parts.length > 1 ? 1 : 0]?.[0] ?? '?'
  }
  return '?'
}

/** ประกอบชื่อเต็มจาก parts ย่อย (fallback กรณีไม่มี field name) */
function buildFullName(row) {
  return [row.prename_th, row.per_name, row.per_surname]
    .filter(Boolean)
    .join(' ') || '—'
}

/** แปลง ISO datetime → HH:MM:SS (Thai locale) */
function formatTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('th-TH', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
</script>
