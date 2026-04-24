<template>
  <!--
    DashboardView.vue — หน้าหลัก
    ══════════════════════════════════════════════════════════════
    Layout:

    [แถบสถานะ refresh]
    [StatCard ×4]
    ─────────────────────────────────────────────────
    [HourlyChart 2/3] | [OrgBreakdown 1/3]
    ─────────────────────────────────────────────────
    [PersonCards grid — แสดงทุกคนเหมือน GUI panel]
    [AttendanceFeed — รายการล่าสุดแบบตาราง]
    ══════════════════════════════════════════════════════════════
  -->
  <main class="p-4 md:p-6 space-y-4 max-w-screen-2xl mx-auto w-full">

    <!-- ══ แถบสถานะ refresh ════════════════════════════════════════ -->
    <div class="flex items-center justify-between gap-3 text-xs">
      <div class="flex items-center gap-2 text-gui-dim">
        <span
          class="w-2 h-2 rounded-full shrink-0"
          :class="error ? 'bg-gui-fail' : 'bg-gui-in animate-pulse-slow'"
        />
        <span v-if="error" class="text-gui-fail">เชื่อมต่อ API ไม่ได้: {{ error }}</span>
        <span v-else>อัพเดตเมื่อ {{ lastFetchStr }}</span>
      </div>

      <div class="flex items-center gap-2">
        <!-- Clear Today (Test) -->
        <button
          @click="confirmClearToday"
          :disabled="clearing"
          title="ล้างข้อมูลการลงเวลาวันนี้ทั้งหมด + session cache (สำหรับ test เท่านั้น)"
          class="px-3 py-1 rounded-lg border border-gui-fail/30 text-gui-fail/70
                 hover:border-gui-fail/60 hover:text-gui-fail transition-colors
                 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {{ clearing ? 'กำลังล้าง...' : '🗑 Clear Today' }}
        </button>

        <!-- Refresh -->
        <button
          @click="refresh"
          :disabled="loading"
          class="px-3 py-1 rounded-lg border border-gui-border text-gui-dim
                 hover:border-gui-in/40 hover:text-gui-text transition-colors
                 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {{ loading ? 'กำลังโหลด...' : '↻ Refresh' }}
        </button>
      </div>
    </div>

    <!-- ══ Confirm Dialog — Clear Today ══════════════════════════════ -->
    <Teleport to="body">
      <div
        v-if="showConfirm"
        class="fixed inset-0 z-50 flex items-center justify-center
               bg-black/60 backdrop-blur-sm"
        @click.self="showConfirm = false"
      >
        <div class="bg-gui-panel border border-gui-fail/40 rounded-2xl
                    shadow-2xl p-6 w-full max-w-sm mx-4">
          <h3 class="font-bold text-base mb-1 text-gui-text">ยืนยันการล้างข้อมูล</h3>
          <p class="text-sm text-gui-dim mb-1">
            จะ<span class="text-gui-fail font-semibold">ลบข้อมูลการลงเวลาวันนี้ทั้งหมด</span>
            ออกจาก database และล้าง session cache
          </p>
          <p class="text-xs text-gui-dim/70 mb-5">
            ⚠ ใช้สำหรับ testing เท่านั้น — ข้อมูลวันอื่นไม่ได้รับผลกระทบ
          </p>
          <div class="flex gap-3 justify-end">
            <button
              @click="showConfirm = false"
              class="px-4 py-1.5 rounded-lg text-sm border border-gui-border
                     text-gui-dim hover:text-gui-text transition-colors"
            >
              ยกเลิก
            </button>
            <button
              @click="doClearToday"
              class="px-4 py-1.5 rounded-lg text-sm font-semibold
                     bg-gui-fail/15 text-gui-fail border border-gui-fail/40
                     hover:bg-gui-fail/25 transition-colors"
            >
              ยืนยัน ล้างข้อมูล
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ══ Stat Cards ══════════════════════════════════════════════
         ค่าต่างๆ จากระบบ — เหมือน HUD ใน GUI
         ══════════════════════════════════════════════════════════ -->
    <section class="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
      <StatCard
        label="เช็คอินวันนี้"
        :value="stats.totalIn"
        icon="✅"
        color="green"
        sub-label="จำนวนครั้ง IN ทั้งหมด"
      />
      <StatCard
        label="เช็คเอาท์วันนี้"
        :value="stats.totalOut"
        icon="🚪"
        color="yellow"
        sub-label="จำนวนครั้ง OUT ทั้งหมด"
      />
      <StatCard
        label="ยังอยู่ในที่ทำงาน"
        :value="stats.currentlyIn"
        icon="👥"
        color="blue"
        sub-label="IN แต่ยังไม่มี OUT วันนี้"
      />
      <StatCard
        label="พนักงานทั้งหมดวันนี้"
        :value="persons.length"
        icon="🏢"
        color="red"
        sub-label="จำนวนคน (ไม่นับซ้ำ)"
      />
    </section>

    <!-- ══ Chart + Org (2 columns) ═════════════════════════════════
         HourlyChart = 2/3 | OrgBreakdown = 1/3
         ══════════════════════════════════════════════════════════ -->
    <section class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="lg:col-span-2">
        <HourlyChart :hourly="hourly" />
      </div>
      <div>
        <OrgBreakdown :by-org="byOrg" />
      </div>
    </section>

    <!-- ══ Person Cards — เหมือน GUI Right Panel ══════════════════
         แสดงทุกคนที่ระบบตรวจพบวันนี้ พร้อมรูปถ่าย / avatar
         ถ้า main.py รันอยู่: รวมคนที่กำลังอยู่ใน liveness ด้วย (PENDING)
         ถ้า main.py ไม่ได้รัน: แสดงจาก DB เท่านั้น
         เรียง: IN → PENDING → OUT → DB-only

         เพิ่มคอลัมน์: เปลี่ยน grid-cols-* ด้านล่าง
         ══════════════════════════════════════════════════════════ -->
    <section>
      <!-- Header ของ section -->
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold text-sm flex items-center gap-2">
          <span class="text-gui-in">▣</span>
          รายชื่อวันนี้
          <span class="text-xs text-gui-dim font-normal">({{ mergedPersons.length }} คน)</span>
          <!-- LIVE indicator — แสดงเมื่อ main.py กำลังรัน -->
          <span
            v-if="!liveStale"
            class="inline-flex items-center gap-1 text-xs px-1.5 py-0.5
                   rounded bg-gui-in/15 text-gui-in font-semibold"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-gui-in animate-pulse" />
            LIVE
          </span>
        </h2>
        <!-- legend สี -->
        <div class="flex items-center gap-3 text-xs text-gui-dim">
          <span class="flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-gui-in" /> ยังอยู่
          </span>
          <span class="flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-gui-out" /> ออกแล้ว
          </span>
          <!-- เพิ่ม legend "กำลังตรวจ" เมื่อ main.py รัน -->
          <span v-if="!liveStale" class="flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-purple-400" /> กำลังตรวจ
          </span>
        </div>
      </div>

      <!-- Empty state -->
      <div
        v-if="mergedPersons.length === 0"
        class="bg-gui-panel border border-gui-border rounded-xl
               py-12 flex flex-col items-center gap-2 text-gui-dim text-sm"
      >
        <span class="text-4xl">👁</span>
        {{ loading ? 'กำลังโหลด...' : 'ยังไม่มีการลงเวลาวันนี้' }}
      </div>

      <!-- Card Grid — responsive: 2 → 3 → 4 → 5 คอลัมน์ -->
      <div
        v-else
        class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3"
      >
        <PersonCard
          v-for="p in mergedPersons"
          :key="p.per_id"
          :person="p"
          :api-base="API_BASE"
        />
      </div>
    </section>

    <!-- ══ Attendance Feed — รายการแบบตาราง (log ทั้งหมด) ═════════
         แสดงทุก record (ทั้ง IN และ OUT แยกกัน) เรียงใหม่สุดก่อน
         ══════════════════════════════════════════════════════════ -->
    <section style="min-height: 300px">
      <AttendanceFeed :feed="feed" :loading="loading" />
    </section>

  </main>
</template>

<script setup>
import { computed, ref } from 'vue'

// ── Components ────────────────────────────────────────────────────
import StatCard       from '@/components/StatCard.vue'
import PersonCard     from '@/components/PersonCard.vue'
import AttendanceFeed from '@/components/AttendanceFeed.vue'
import HourlyChart    from '@/components/HourlyChart.vue'
import OrgBreakdown   from '@/components/OrgBreakdown.vue'

// ── Composables ───────────────────────────────────────────────────
import { useAttendance }  from '@/composables/useAttendance.js'
import { useLiveSession } from '@/composables/useLiveSession.js'

const {
  stats,      // { totalIn, totalOut, currentlyIn, total }
  byOrg,      // Array<{ name, in, out, total }>
  hourly,     // Array<{ hour, in, out }>  ยาว 24 ตัว
  feed,       // รายการทุก record เรียงใหม่สุดก่อน
  persons,    // Array per-person summary (รวม IN+OUT ต่อคน)
  loading,
  error,
  lastFetch,
  refresh,
} = useAttendance()

// ── Live Session (จาก main.py ผ่าน live_state.json) ───────────────
const {
  stale:   liveStale,    // true ถ้า main.py ไม่ได้รัน / หยุดส่งข้อมูล
  persons: livePersons,  // Array ของคนที่ main.py กำลังตรวจอยู่ตอนนี้
} = useLiveSession()

// ── Merged persons: live session + DB ────────────────────────────
// ตรรกะเหมือน main.py right panel:
//   - ถ้า main.py รันอยู่ (not stale): แสดงคนจาก live session ก่อน
//     รวมถึงคนที่ยังอยู่ในขั้น liveness (PENDING) ด้วย
//   - ถ้า main.py ไม่ได้รัน (stale): แสดงข้อมูลจาก DB เท่านั้น
const mergedPersons = computed(() => {
  // stale = main.py offline → ใช้ DB data เท่านั้น
  if (liveStale.value) return persons.value

  // Build lookup จาก DB
  const dbMap  = Object.fromEntries(persons.value.map(p => [p.per_id, p]))
  const liveSet = new Set(livePersons.value.map(p => p.per_id))

  // Live persons (รวมคนที่ยังอยู่ใน liveness checking)
  const result = livePersons.value.map(lp => {
    const db = dbMap[lp.per_id]
    return {
      per_id:       lp.per_id,
      name:         lp.display_name || lp.per_id,
      prename_th:   db?.prename_th  || '',
      per_name:     lp.per_name,
      per_surname:  lp.per_surname,
      posname_th:   lp.posname_th,
      organize_th:  lp.organize_th,
      in_time:      db?.in_time   || lp.first_seen || null,
      out_time:     db?.out_time  || null,
      // status: ตามสถานะ session (PENDING = ยังไม่ผ่าน liveness/ยังไม่ check-in)
      status:       lp.checked_in ? (lp.checked_out ? 'OUT' : 'IN') : 'PENDING',
      liveness:     lp.liveness,
      liveness_msg: lp.liveness_msg,
    }
  })

  // เพิ่มคนที่อยู่ใน DB แต่ไม่อยู่ใน live session (ออกไปแล้ว / session ก่อนหน้า)
  persons.value.forEach(dbP => {
    if (!liveSet.has(dbP.per_id))
      result.push({ ...dbP, liveness: null, liveness_msg: null })
  })

  // Sort: FIFO — เรียงตาม in_time เก่าสุดขึ้นก่อน (คนเข้าก่อนแสดงก่อน)
  // คนที่ยังไม่มี in_time (PENDING ที่เพิ่งตรวจเจอ) อยู่ท้ายสุด
  return result.sort((a, b) => {
    const aTime = a.in_time ? new Date(a.in_time).getTime() : Infinity
    const bTime = b.in_time ? new Date(b.in_time).getTime() : Infinity
    return aTime - bTime
  })
})

// ── Config ────────────────────────────────────────────────────────
const API_BASE       = import.meta.env.VITE_API_BASE_URL ?? '/api'
const CLEAR_TODAY_URL = `${API_BASE}/attendance/today/all`

// ── Clear Today (Test) ────────────────────────────────────────────
const showConfirm = ref(false)
const clearing    = ref(false)

function confirmClearToday() {
  showConfirm.value = true
}

async function doClearToday() {
  showConfirm.value = false
  clearing.value    = true
  try {
    await fetch(CLEAR_TODAY_URL, { method: 'DELETE' })
    await refresh()   // โหลดข้อมูลใหม่ทันที
  } catch { /* ignore */ } finally {
    clearing.value = false
  }
}

// ── แปลง lastFetch → "Xs ที่แล้ว" ────────────────────────────────
const now = ref(new Date())
setInterval(() => { now.value = new Date() }, 5000)

const lastFetchStr = computed(() => {
  if (!lastFetch.value) return 'รอข้อมูล...'
  const diff = Math.floor((now.value - lastFetch.value) / 1000)
  if (diff < 60) return `${diff} วินาทีที่แล้ว`
  return `${Math.floor(diff / 60)} นาทีที่แล้ว`
})
</script>
