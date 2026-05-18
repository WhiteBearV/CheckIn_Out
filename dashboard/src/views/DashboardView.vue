<template>
  <main class="p-4 md:p-6 space-y-4 max-w-screen-2xl mx-auto w-full">

    <!-- แถบสถานะ refresh -->
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
        <button
          v-if="hasPermission('attendance.clear')"
          @click="confirmClearToday"
          :disabled="clearing"
          title="ล้างข้อมูลการลงเวลาวันนี้ทั้งหมด + session cache (สำหรับ test เท่านั้น)"
          class="px-3 py-1 rounded-lg border border-gui-fail/30 text-gui-fail/70
                 hover:border-gui-fail/60 hover:text-gui-fail transition-colors
                 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {{ clearing ? 'กำลังล้าง...' : '🗑 Clear Today' }}
        </button>
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

    <!-- Confirm Dialog -->
    <Teleport to="body">
      <div
        v-if="showConfirm"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        @click.self="showConfirm = false"
      >
        <div class="bg-gui-panel border border-gui-fail/40 rounded-2xl shadow-2xl p-6 w-full max-w-sm mx-4">
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
              class="px-4 py-1.5 rounded-lg text-sm border border-gui-border text-gui-dim hover:text-gui-text transition-colors"
            >ยกเลิก</button>
            <button
              @click="doClearToday"
              class="px-4 py-1.5 rounded-lg text-sm font-semibold bg-gui-fail/15 text-gui-fail border border-gui-fail/40 hover:bg-gui-fail/25 transition-colors"
            >ยืนยัน ล้างข้อมูล</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Stat Cards -->
    <section class="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
      <StatCard label="เช็คอินวันนี้"       :value="stats.totalIn"     icon="✅" color="green"  sub-label="จำนวนครั้ง IN ทั้งหมด" />
      <StatCard label="เช็คเอาท์วันนี้"     :value="stats.totalOut"    icon="🚪" color="yellow" sub-label="จำนวนครั้ง OUT ทั้งหมด" />
      <StatCard label="ยังอยู่ในที่ทำงาน"   :value="stats.currentlyIn" icon="👥" color="blue"   sub-label="IN แต่ยังไม่มี OUT วันนี้" />
      <StatCard label="พนักงานทั้งหมดวันนี้" :value="persons.length"    icon="🏢" color="red"    sub-label="จำนวนคน (ไม่นับซ้ำ)" />
    </section>

    <!-- Chart + Org -->
    <section class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="lg:col-span-2"><HourlyChart :hourly="hourly" /></div>
      <div><OrgBreakdown :by-org="byOrg" /></div>
    </section>

    <!-- รายชื่อที่พบวันนี้ (live + DB merged) -->
    <section>
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold text-sm flex items-center gap-2">
          <span class="text-gui-in">▣</span>
          รายชื่อที่พบวันนี้
          <span class="text-xs text-gui-dim font-normal">({{ mergedPersons.length }} คน)</span>
          <span v-if="!liveStale"
            class="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-gui-in/15 text-gui-in font-semibold">
            <span class="w-1.5 h-1.5 rounded-full bg-gui-in animate-pulse" />
            LIVE
          </span>
        </h2>
        <div class="flex items-center gap-3 text-xs text-gui-dim">
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-gui-in" /> ยังอยู่</span>
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-gui-out" /> ออกแล้ว</span>
          <span v-if="!liveStale" class="flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-purple-400" /> กำลังตรวจ
          </span>
        </div>
      </div>

      <div v-if="mergedPersons.length === 0"
        class="bg-gui-panel border border-gui-border rounded-xl py-12 flex flex-col items-center gap-2 text-gui-dim text-sm">
        <span class="text-4xl">👁</span>
        {{ loading ? 'กำลังโหลด...' : 'ยังไม่มีการลงเวลาวันนี้' }}
      </div>

      <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        <PersonCard
          v-for="p in mergedPersons"
          :key="p.per_id"
          :person="p"
          :api-base="API_BASE"
        />
      </div>
    </section>

    <!-- รายชื่อเช็คชื่อเข้าออก (DB) -->
    <section>
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold text-sm flex items-center gap-2">
          <span class="text-gui-out">▣</span>
          รายชื่อเช็คชื่อเข้าออก
          <span class="text-xs text-gui-dim font-normal">({{ persons.length }} คน)</span>
        </h2>
        <div class="flex items-center gap-3 text-xs text-gui-dim">
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-gui-in" /> ยังอยู่</span>
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-gui-out" /> ออกแล้ว</span>
        </div>
      </div>

      <div v-if="persons.length === 0"
        class="bg-gui-panel border border-gui-border rounded-xl py-12 flex flex-col items-center gap-2 text-gui-dim text-sm">
        <span class="text-4xl">📋</span>
        {{ loading ? 'กำลังโหลด...' : 'ยังไม่มีการเช็คชื่อวันนี้' }}
      </div>

      <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        <PersonCard
          v-for="p in persons"
          :key="`feed-${p.per_id}`"
          :person="p"
          :api-base="API_BASE"
          photo-mode="verify"
        />
      </div>
    </section>

  </main>
</template>

<script setup>
import { computed, ref } from 'vue'

import StatCard     from '@/components/StatCard.vue'
import PersonCard   from '@/components/PersonCard.vue'
import HourlyChart  from '@/components/HourlyChart.vue'
import OrgBreakdown from '@/components/OrgBreakdown.vue'

import { useAttendance }  from '@/composables/useAttendance.js'
import { useLiveSession } from '@/composables/useLiveSession.js'
import { apiDelete }      from '@/api/attendance.js'
import { hasPermission }  from '@/composables/useAuth.js'

const {
  stats,
  byOrg,
  hourly,
  persons,
  loading,
  error,
  lastFetch,
  refresh,
} = useAttendance()

const {
  stale:   liveStale,
  persons: livePersons,
} = useLiveSession()

const mergedPersons = computed(() => {
  if (liveStale.value) return persons.value

  const dbMap   = Object.fromEntries(persons.value.map(p => [p.per_id, p]))
  const liveSet = new Set(livePersons.value.map(p => p.per_id))

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
      status:       lp.checked_in ? (lp.checked_out ? 'OUT' : 'IN') : 'PENDING',
      liveness:     lp.liveness,
      liveness_msg: lp.liveness_msg,
    }
  })

  persons.value.forEach(dbP => {
    if (!liveSet.has(dbP.per_id))
      result.push({ ...dbP, liveness: null, liveness_msg: null })
  })

  return result.sort((a, b) => {
    const aTime = a.in_time ? new Date(a.in_time).getTime() : Infinity
    const bTime = b.in_time ? new Date(b.in_time).getTime() : Infinity
    return aTime - bTime
  })
})

const API_BASE        = import.meta.env.VITE_API_BASE_URL ?? '/api'
const CLEAR_TODAY_URL = `${API_BASE}/attendance/today/all`

const showConfirm = ref(false)
const clearing    = ref(false)

function confirmClearToday() { showConfirm.value = true }

async function doClearToday() {
  showConfirm.value = false
  clearing.value    = true
  try {
    await apiDelete('/attendance/today/all')
    await refresh()
  } catch { /* ignore */ } finally {
    clearing.value = false
  }
}

const now = ref(new Date())
setInterval(() => { now.value = new Date() }, 5000)

const lastFetchStr = computed(() => {
  if (!lastFetch.value) return 'รอข้อมูล...'
  const diff = Math.floor((now.value - lastFetch.value) / 1000)
  if (diff < 60) return `${diff} วินาทีที่แล้ว`
  return `${Math.floor(diff / 60)} นาทีที่แล้ว`
})
</script>
