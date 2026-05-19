<template>
  <main class="p-4 md:p-6 space-y-4 max-w-screen-2xl mx-auto w-full">

    <!-- ── Header ──────────────────────────────────────────────────────────── -->
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="font-semibold text-base text-gui-text flex items-center gap-2">
        <span class="text-gui-out">📋</span>
        ประวัติการลงเวลา
      </h1>
      <span class="text-xs text-gui-dim">{{ dateRangeLabel }}</span>
      <div class="ml-auto flex items-center gap-2">
        <span class="text-xs text-gui-dim">{{ filteredPersons.length }} คน</span>
        <span v-if="!loading" class="text-[10px] text-gui-dim/40 flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-gui-in/50 animate-pulse" />
          อัปเดตทุก 30s
        </span>
        <button @click="exportCSV" :disabled="filteredPersons.length === 0"
          class="px-3 py-1.5 rounded-lg text-xs border border-gui-border text-gui-dim
                 hover:text-gui-text hover:border-gui-in/40 transition-colors
                 disabled:opacity-30 disabled:cursor-not-allowed">
          ⬇ CSV
        </button>
        <button @click="exportPDF" :disabled="filteredPersons.length === 0"
          class="px-3 py-1.5 rounded-lg text-xs border border-gui-border text-gui-dim
                 hover:text-gui-text hover:border-gui-in/40 transition-colors
                 disabled:opacity-30 disabled:cursor-not-allowed">
          ⬇ PDF
        </button>
      </div>
    </div>

    <!-- ── Date Range Selector ────────────────────────────────────────────── -->
    <div class="bg-gui-panel border border-gui-border rounded-xl p-3 space-y-2.5">
      <!-- Preset pills -->
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="p in PRESETS" :key="p.key"
          @click="selectPreset(p.key)"
          class="px-3 py-1.5 rounded-lg text-xs border transition-colors"
          :class="preset === p.key
            ? 'border-gui-in/50 bg-gui-in/15 text-gui-in font-medium'
            : 'border-gui-border text-gui-dim hover:text-gui-text hover:border-gui-in/30'"
        >{{ p.label }}</button>
      </div>
      <!-- Custom date range inputs -->
      <div v-if="preset === 'custom'" class="flex flex-wrap items-center gap-2">
        <span class="text-xs text-gui-dim">จาก</span>
        <input v-model="customStart" type="date" :max="customEnd"
          class="px-3 py-1.5 rounded-lg text-xs border border-gui-border bg-gui-bg
                 text-gui-text focus:outline-none focus:border-gui-in/60 transition-colors" />
        <span class="text-xs text-gui-dim">ถึง</span>
        <input v-model="customEnd" type="date" :min="customStart" :max="todayISO"
          class="px-3 py-1.5 rounded-lg text-xs border border-gui-border bg-gui-bg
                 text-gui-text focus:outline-none focus:border-gui-in/60 transition-colors" />
        <span class="text-xs text-gui-dim/60">({{ totalDays }} วัน)</span>
      </div>
    </div>

    <!-- ── Filters ────────────────────────────────────────────────────────── -->
    <div class="flex flex-wrap items-center gap-3">
      <!-- Search -->
      <input v-model="searchQuery" type="text" placeholder="ค้นหาชื่อ / หน่วยงาน..."
        class="flex-1 min-w-[180px] max-w-xs px-3 py-1.5 rounded-lg text-sm
               border border-gui-border bg-gui-bg text-gui-text
               placeholder-gui-dim/50 focus:outline-none focus:border-gui-in/60 transition-colors" />
      <!-- Org filter -->
      <select v-model="orgFilter"
        class="px-3 py-1.5 rounded-lg text-xs border border-gui-border bg-gui-bg
               text-gui-text focus:outline-none focus:border-gui-in/60 transition-colors">
        <option value="all">ทุกหน่วยงาน</option>
        <option v-for="org in orgs" :key="org" :value="org">{{ org }}</option>
      </select>
      <!-- Status filter -->
      <div class="flex gap-1">
        <button
          v-for="f in STATUS_FILTERS" :key="f.value"
          @click="statusFilter = f.value"
          class="px-3 py-1.5 rounded-lg text-xs border transition-colors"
          :class="statusFilter === f.value
            ? 'border-gui-in/50 bg-gui-in/15 text-gui-in font-medium'
            : 'border-gui-border text-gui-dim hover:text-gui-text hover:border-gui-in/30'"
        >{{ f.label }}</button>
      </div>
    </div>

    <!-- ── Stat Cards ─────────────────────────────────────────────────────── -->
    <section class="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <div v-for="s in statCards" :key="s.label"
        class="bg-gui-panel border border-gui-border rounded-xl px-4 py-3 flex items-center gap-3">
        <span class="text-2xl">{{ s.icon }}</span>
        <div>
          <div class="text-xl font-bold tabular-nums" :class="s.color">{{ s.value }}</div>
          <div class="text-xs text-gui-dim">{{ s.label }}</div>
        </div>
      </div>
    </section>

    <!-- ── Table ──────────────────────────────────────────────────────────── -->
    <section>
      <div v-if="error"
        class="bg-gui-fail/10 border border-gui-fail/30 rounded-xl p-4 text-sm text-gui-fail">
        เชื่อมต่อ API ไม่ได้: {{ error }}
      </div>
      <div v-else class="bg-gui-panel border border-gui-border rounded-xl overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gui-border text-gui-dim text-xs uppercase tracking-wide">
              <th class="text-left px-4 py-3 font-medium">ชื่อ-นามสกุล</th>
              <th class="text-left px-4 py-3 font-medium hidden md:table-cell">หน่วยงาน / ตำแหน่ง</th>
              <th class="text-center px-3 py-3 font-medium">เข้างาน</th>
              <th class="text-center px-3 py-3 font-medium hidden sm:table-cell">เข้ารอบแรก</th>
              <th class="text-center px-3 py-3 font-medium hidden sm:table-cell">ออกล่าสุด</th>
              <th class="text-center px-3 py-3 font-medium">สถานะ</th>
              <th class="px-3 py-3 w-6"></th>
            </tr>
          </thead>
          <tbody>
            <!-- loading -->
            <tr v-if="loading">
              <td colspan="7" class="text-center py-12 text-gui-dim">
                <span class="animate-pulse">กำลังโหลด...</span>
              </td>
            </tr>
            <!-- empty -->
            <tr v-else-if="filteredPersons.length === 0">
              <td colspan="7" class="text-center py-12">
                <div class="flex flex-col items-center gap-2 text-gui-dim">
                  <span class="text-3xl">📭</span>
                  <span class="text-sm">
                    {{ persons.length === 0
                      ? `ไม่มีข้อมูลในช่วง ${dateRangeLabel}`
                      : 'ไม่มีข้อมูลตรงกับที่ค้นหา' }}
                  </span>
                </div>
              </td>
            </tr>
            <!-- rows -->
            <tr
              v-else
              v-for="p in filteredPersons" :key="p.per_id"
              class="border-b border-gui-border/50 hover:bg-gui-bg/40 transition-colors cursor-pointer"
              @click="openDetail(p)"
            >
              <!-- ชื่อ + avatar -->
              <td class="px-4 py-3">
                <div class="flex items-center gap-2.5">
                  <div class="w-8 h-8 rounded-full shrink-0 overflow-hidden ring-1 flex items-center justify-center"
                    :class="p.status === 'IN' ? 'ring-gui-in/40 bg-gui-in/10' : 'ring-gui-out/30 bg-gui-out/10'">
                    <img v-if="!failedPhotos.has(p.per_id)"
                      :src="`${API_BASE}/person-profile/${p.per_id}`"
                      class="w-full h-full object-cover"
                      @error="failedPhotos.add(p.per_id)" alt="" />
                    <span v-else class="text-xs font-bold"
                      :class="p.status === 'IN' ? 'text-gui-in' : 'text-gui-out'">
                      {{ (p.per_name || p.name || '?')[0] }}
                    </span>
                  </div>
                  <div>
                    <div class="font-medium text-gui-text text-sm leading-snug">{{ displayName(p) }}</div>
                    <div class="text-[11px] text-gui-dim/60 font-mono">{{ maskedPid(p.per_id) }}</div>
                  </div>
                </div>
              </td>
              <!-- หน่วยงาน / ตำแหน่ง -->
              <td class="px-4 py-3 hidden md:table-cell">
                <div class="text-xs text-gui-text truncate max-w-[200px]">{{ p.organize_th || '—' }}</div>
                <div class="text-[11px] text-gui-dim truncate max-w-[200px]">{{ p.posname_th || '—' }}</div>
              </td>
              <!-- จำนวนวันเข้างาน -->
              <td class="px-3 py-3 text-center">
                <span class="text-sm font-bold tabular-nums"
                  :class="p.daysCount > 0 ? 'text-gui-in' : 'text-gui-dim/40'">
                  {{ p.daysCount }}
                </span>
                <span class="text-[10px] text-gui-dim/60"> / {{ totalDays }} วัน</span>
              </td>
              <!-- เข้ารอบแรก -->
              <td class="px-3 py-3 text-center hidden sm:table-cell">
                <span class="font-mono text-xs tabular-nums"
                  :class="p.firstIn ? 'text-gui-in' : 'text-gui-dim/40'">
                  {{ p.firstIn ? fmtDateTimeShort(p.firstIn) : '——' }}
                </span>
              </td>
              <!-- ออกล่าสุด -->
              <td class="px-3 py-3 text-center hidden sm:table-cell">
                <span class="font-mono text-xs tabular-nums"
                  :class="p.latestOut ? 'text-gui-out' : 'text-gui-dim/30'">
                  {{ p.latestOut ? fmtDateTimeShort(p.latestOut) : '——' }}
                </span>
              </td>
              <!-- สถานะ -->
              <td class="px-3 py-3 text-center">
                <span class="px-2 py-0.5 rounded-full text-xs font-semibold border"
                  :class="p.status === 'IN'
                    ? 'bg-gui-in/15 text-gui-in border-gui-in/30'
                    : 'bg-gui-out/15 text-gui-out border-gui-out/30'">
                  {{ p.status === 'IN' ? 'ยังอยู่' : 'ออกแล้ว' }}
                </span>
              </td>
              <!-- arrow -->
              <td class="px-3 py-3 text-center text-gui-dim/40 text-sm">›</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

  </main>

  <!-- ── Person Detail Modal ───────────────────────────────────────────────── -->
  <Teleport to="body">
    <div v-if="selectedPerson"
      class="fixed inset-0 z-[10000] flex items-start justify-center
             bg-black/60 backdrop-blur-sm overflow-y-auto pt-10 pb-6"
      @click.self="closeDetail">
      <div class="bg-gui-panel border border-gui-border rounded-2xl shadow-2xl w-full max-w-lg mx-4 my-auto">

        <!-- Modal Header -->
        <div class="flex items-center gap-3 px-5 py-4 border-b border-gui-border">
          <div class="w-10 h-10 rounded-full overflow-hidden shrink-0 ring-2 flex items-center justify-center"
            :class="selectedPerson.status === 'IN' ? 'ring-gui-in/50 bg-gui-in/10' : 'ring-gui-out/30 bg-gui-out/10'">
            <img v-if="!failedPhotos.has(selectedPerson.per_id)"
              :src="`${API_BASE}/person-profile/${selectedPerson.per_id}`"
              class="w-full h-full object-cover"
              @error="failedPhotos.add(selectedPerson.per_id)" alt="" />
            <span v-else class="font-bold text-sm"
              :class="selectedPerson.status === 'IN' ? 'text-gui-in' : 'text-gui-out'">
              {{ (selectedPerson.per_name || selectedPerson.name || '?')[0] }}
            </span>
          </div>
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-gui-text truncate">{{ displayName(selectedPerson) }}</div>
            <div class="text-xs text-gui-dim truncate">
              {{ [selectedPerson.organize_th, selectedPerson.posname_th].filter(Boolean).join(' · ') || '—' }}
            </div>
          </div>
          <button @click="closeDetail"
            class="text-gui-dim hover:text-gui-text transition-colors text-lg leading-none shrink-0">✕</button>
        </div>

        <!-- Attendance summary -->
        <div class="grid grid-cols-2 sm:grid-cols-4 border-b border-gui-border divide-x divide-gui-border">
          <div class="py-3 text-center">
            <div class="text-2xl font-bold text-gui-in tabular-nums">{{ selectedPerson.daysCount }}</div>
            <div class="text-[10px] text-gui-dim uppercase tracking-wider mt-0.5">วันที่เข้า</div>
          </div>
          <div class="py-3 text-center">
            <div class="text-2xl font-bold text-gui-text tabular-nums">{{ totalDays }}</div>
            <div class="text-[10px] text-gui-dim uppercase tracking-wider mt-0.5">วันในช่วง</div>
          </div>
          <div class="py-3 text-center">
            <div class="text-2xl font-bold tabular-nums"
              :class="attendRate(selectedPerson) >= 80 ? 'text-gui-in'
                    : attendRate(selectedPerson) >= 50 ? 'text-yellow-400'
                    : 'text-gui-fail'">
              {{ attendRate(selectedPerson) }}%
            </div>
            <div class="text-[10px] text-gui-dim uppercase tracking-wider mt-0.5">อัตราเข้างาน</div>
          </div>
          <div class="py-3 text-center col-span-2 sm:col-span-1 border-t sm:border-t-0 border-gui-border">
            <div class="font-mono font-bold text-gui-in leading-tight tabular-nums"
              :class="selectedPerson.firstIn ? 'text-sm' : 'text-2xl'">
              {{ selectedPerson.firstIn ? fmtDateTimeShort(selectedPerson.firstIn) : '——' }}
            </div>
            <div class="text-[10px] text-gui-dim uppercase tracking-wider mt-0.5">เข้ารอบแรก</div>
          </div>
        </div>

        <!-- Range label -->
        <div class="px-5 py-2 text-xs text-gui-dim/60 border-b border-gui-border/40">
          ช่วงวันที่: {{ dateRangeLabel }}
        </div>

        <!-- Daily records -->
        <div class="overflow-y-auto" style="max-height: 380px">
          <table class="w-full text-sm">
            <thead class="sticky top-0 bg-gui-panel border-b border-gui-border">
              <tr class="text-gui-dim text-xs uppercase tracking-wide">
                <th class="text-left px-5 py-2.5 font-medium">วันที่</th>
                <th class="text-center px-3 py-2.5 font-medium">เข้างาน</th>
                <th class="text-center px-3 py-2.5 font-medium">ออกงาน</th>
                <th class="text-center px-3 py-2.5 font-medium">ระยะเวลา</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="([d, times]) in selectedPerson.dayEntries" :key="d"
                class="border-b border-gui-border/40 hover:bg-gui-bg/30 transition-colors"
              >
                <td class="px-5 py-2.5 text-xs text-gui-text font-medium">{{ fmtDateFull(d) }}</td>
                <td class="px-3 py-2.5 text-center font-mono text-xs tabular-nums font-semibold"
                  :class="times.in ? 'text-gui-in' : 'text-gui-dim/40'">
                  {{ times.in ? fmtTime(times.in) : '——' }}
                </td>
                <td class="px-3 py-2.5 text-center font-mono text-xs tabular-nums font-semibold"
                  :class="times.out ? 'text-gui-out' : 'text-gui-dim/30'">
                  {{ times.out ? fmtTime(times.out) : '——' }}
                </td>
                <td class="px-3 py-2.5 text-center text-xs text-gui-dim tabular-nums">
                  {{ calcDuration(times.in, times.out) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Modal Footer -->
        <div class="px-5 py-3 border-t border-gui-border flex justify-end">
          <button @click="closeDetail"
            class="px-4 py-1.5 rounded-lg text-sm border border-gui-border text-gui-dim
                   hover:text-gui-text transition-colors">
            ปิด
          </button>
        </div>

      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { fetchAttendanceRange } from '@/api/attendance.js'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

// ── Constants ──────────────────────────────────────────────────────────────────
const PRESETS = [
  { key: 'today', label: 'วันนี้'    },
  { key: '3d',    label: '3 วัน'    },
  { key: '5d',    label: '5 วัน'    },
  { key: '7d',    label: '7 วัน'    },
  { key: '1m',    label: 'เดือนนี้'  },
  { key: 'custom',label: 'กำหนดเอง' },
]

const STATUS_FILTERS = [
  { value: 'all', label: 'ทั้งหมด' },
  { value: 'IN',  label: 'ยังอยู่'  },
  { value: 'OUT', label: 'ออกแล้ว' },
]

// ── Date helpers ───────────────────────────────────────────────────────────────
function localISO(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const todayISO = localISO(new Date())

function addDays(iso, delta) {
  const d = new Date(iso + 'T00:00:00')
  d.setDate(d.getDate() + delta)
  return localISO(d)
}

function firstOfMonth() {
  const d = new Date()
  d.setDate(1)
  return localISO(d)
}

// ── State ──────────────────────────────────────────────────────────────────────
const preset         = ref('7d')
const customStart    = ref(addDays(todayISO, -6))
const customEnd      = ref(todayISO)
const searchQuery    = ref('')
const orgFilter      = ref('all')
const statusFilter   = ref('all')
const records        = ref([])
const loading        = ref(false)
const error          = ref(null)
const failedPhotos   = ref(new Set())
const selectedPerson = ref(null)

// ── Date Range ─────────────────────────────────────────────────────────────────
const startDate = computed(() => {
  switch (preset.value) {
    case 'today':  return todayISO
    case '3d':     return addDays(todayISO, -2)
    case '5d':     return addDays(todayISO, -4)
    case '7d':     return addDays(todayISO, -6)
    case '1m':     return firstOfMonth()
    case 'custom': return customStart.value
    default:       return todayISO
  }
})

const endDate = computed(() =>
  preset.value === 'custom' ? customEnd.value : todayISO
)

const totalDays = computed(() => {
  const diff = new Date(endDate.value + 'T00:00:00') - new Date(startDate.value + 'T00:00:00')
  return Math.round(diff / 86400000) + 1
})

function selectPreset(key) {
  if (key === 'custom') {
    customStart.value = addDays(todayISO, -6)
    customEnd.value   = todayISO
  }
  preset.value = key
}

// ── Fetch ──────────────────────────────────────────────────────────────────────
async function fetchData() {
  loading.value = true
  error.value   = null
  failedPhotos.value = new Set()
  try {
    records.value = await fetchAttendanceRange(startDate.value, endDate.value)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function silentRefresh() {
  try {
    records.value = await fetchAttendanceRange(startDate.value, endDate.value)
  } catch { /* ไม่แสดง error ระหว่าง background refresh */ }
}

let _pollTimer = null
onMounted(() => {
  fetchData()
  _pollTimer = setInterval(silentRefresh, 30_000)
})
onUnmounted(() => clearInterval(_pollTimer))

watch([startDate, endDate], fetchData)

// ── Org list ───────────────────────────────────────────────────────────────────
const orgs = computed(() =>
  [...new Set(records.value.map(r => r.organize_th).filter(Boolean))].sort()
)

// ── Person aggregation ─────────────────────────────────────────────────────────
const persons = computed(() => {
  const map = {}
  for (const r of records.value) {
    if (!r.per_id) continue
    if (!map[r.per_id]) {
      map[r.per_id] = {
        per_id:      r.per_id,
        name:        r.name        || '',
        prename_th:  r.prename_th  || '',
        per_name:    r.per_name    || '',
        per_surname: r.per_surname || '',
        posname_th:  r.posname_th  || '',
        organize_th: r.organize_th || '',
        days: {},
      }
    }
    const d = r.check_time?.slice(0, 10)
    if (!d) continue
    if (!map[r.per_id].days[d]) map[r.per_id].days[d] = { in: null, out: null }
    if (r.status === 'IN') {
      const cur = map[r.per_id].days[d].in
      if (!cur || r.check_time < cur) map[r.per_id].days[d].in = r.check_time
    } else if (r.status === 'OUT') {
      const cur = map[r.per_id].days[d].out
      if (!cur || r.check_time > cur) map[r.per_id].days[d].out = r.check_time
    }
  }
  return Object.values(map).map(p => {
    const entries = Object.entries(p.days).sort(([a], [b]) => b.localeCompare(a))
    const latest  = entries[0]
    const allIns  = Object.values(p.days).map(t => t.in).filter(Boolean)
    const firstIn = allIns.length ? allIns.reduce((a, b) => a < b ? a : b) : null
    return {
      ...p,
      dayEntries: entries,
      daysCount:  entries.length,
      firstIn,
      latestIn:   latest?.[1].in  ?? null,
      latestOut:  latest?.[1].out ?? null,
      status: latest ? (latest[1].out ? 'OUT' : 'IN') : 'IN',
    }
  })
})

// ── Filtered ───────────────────────────────────────────────────────────────────
const filteredPersons = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  return persons.value.filter(p => {
    if (orgFilter.value !== 'all' && p.organize_th !== orgFilter.value) return false
    if (statusFilter.value !== 'all' && p.status !== statusFilter.value) return false
    if (!q) return true
    return (
      displayName(p).toLowerCase().includes(q) ||
      (p.organize_th || '').toLowerCase().includes(q) ||
      (p.posname_th  || '').toLowerCase().includes(q)
    )
  })
})

// ── Stat Cards ─────────────────────────────────────────────────────────────────
const statCards = computed(() => [
  {
    label: 'เช็คอิน (ครั้ง)',
    value: records.value.filter(r => r.status === 'IN').length,
    icon: '✅', color: 'text-gui-in',
  },
  {
    label: 'เช็คเอาท์ (ครั้ง)',
    value: records.value.filter(r => r.status === 'OUT').length,
    icon: '🚪', color: 'text-gui-out',
  },
  {
    label: 'คนทั้งหมด',
    value: persons.value.length,
    icon: '👥', color: 'text-blue-400',
  },
  {
    label: 'ช่วงเวลา',
    value: `${totalDays.value} วัน`,
    icon: '📅', color: 'text-gui-text',
  },
])

// ── Modal ──────────────────────────────────────────────────────────────────────
function openDetail(p) { selectedPerson.value = p }
function closeDetail()  { selectedPerson.value = null }

function attendRate(p) {
  return totalDays.value ? Math.round((p.daysCount / totalDays.value) * 100) : 0
}

// ── Formatters ─────────────────────────────────────────────────────────────────
function displayName(p) {
  if (p.name) return p.name
  return [p.prename_th, p.per_name, p.per_surname].filter(Boolean).join(' ') || p.per_id
}

function maskedPid(pid) {
  const s = String(pid ?? '')
  return s.length <= 4 ? s : '•'.repeat(s.length - 4) + s.slice(-4)
}

function fmtTime(iso) {
  if (!iso) return '——'
  return new Date(iso).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
}

function fmtDateTimeShort(iso) {
  if (!iso) return '——'
  const d = new Date(iso)
  return (
    d.toLocaleDateString('th-TH', { day: 'numeric', month: 'short' }) +
    ' ' +
    d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
  )
}

function fmtDateFull(isoDate) {
  if (!isoDate) return '——'
  return new Date(isoDate + 'T00:00:00').toLocaleDateString('th-TH', {
    weekday: 'short', day: 'numeric', month: 'long', year: 'numeric',
  })
}

function calcDuration(inIso, outIso) {
  if (!inIso || !outIso) return '—'
  const diffMin = Math.round((new Date(outIso) - new Date(inIso)) / 60000)
  if (diffMin < 0) return '—'
  const h = Math.floor(diffMin / 60)
  const m = diffMin % 60
  return h > 0 ? `${h}ชม. ${m}น.` : `${m}น.`
}

const dateRangeLabel = computed(() => {
  if (startDate.value === endDate.value) {
    return new Date(startDate.value + 'T00:00:00').toLocaleDateString('th-TH', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    })
  }
  return (
    new Date(startDate.value + 'T00:00:00').toLocaleDateString('th-TH', { day: 'numeric', month: 'short' }) +
    ' – ' +
    new Date(endDate.value + 'T00:00:00').toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: 'numeric' })
  )
})

// ── Export CSV ─────────────────────────────────────────────────────────────────
function exportCSV() {
  const headers = ['ชื่อ-นามสกุล', 'หน่วยงาน', 'ตำแหน่ง', 'วันที่เข้า', 'เข้าล่าสุด', 'ออกล่าสุด', 'สถานะ']
  const rows = filteredPersons.value.map(p => [
    displayName(p),
    p.organize_th || '',
    p.posname_th  || '',
    p.daysCount,
    p.latestIn  ? fmtDateTimeShort(p.latestIn)  : '',
    p.latestOut ? fmtDateTimeShort(p.latestOut) : '',
    p.status === 'IN' ? 'ยังอยู่' : 'ออกแล้ว',
  ])
  const csv = [headers, ...rows]
    .map(row => row.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))
    .join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `attendance_${startDate.value}_to_${endDate.value}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 100)
}

function exportPDF() { window.print() }
</script>
