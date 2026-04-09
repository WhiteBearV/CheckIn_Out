<template>
  <div class="p-4 md:p-6 max-w-screen-2xl mx-auto w-full space-y-4">

    <!-- ════ FULLSCREEN WRAPPER: กล้อง + รายชื่อวันนี้ ════════════════ -->
    <div
      ref="fullscreenWrapper"
      :class="isFullscreen
        ? 'flex flex-row bg-[#0a0a0a] overflow-hidden'
        : 'grid grid-cols-1 lg:grid-cols-3 gap-4'"
      style="min-height: 520px"
    >

      <!-- ── กล้อง (ซ้าย) ─────────────────────────────────────────── -->
      <div
        ref="cameraContainer"
        class="bg-black flex flex-col overflow-hidden"
        :class="isFullscreen
          ? 'flex-1 border-r border-gui-border'
          : 'lg:col-span-2 rounded-xl border border-gui-border'"
      >

        <!-- Header -->
        <div class="px-4 py-3 border-b border-gui-border flex items-center justify-between shrink-0 bg-gui-panel">
          <h2 class="font-semibold text-sm flex items-center gap-2">
            <span
              class="w-2 h-2 rounded-full shrink-0 transition-colors"
              :class="{
                'bg-gui-in animate-pulse-slow': isLive,
                'bg-gui-out animate-pulse':     isStarting,
                'bg-gui-dim':                   !isLive && !isStarting,
              }"
            />
            Face Recognition
          </h2>
          <span
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="{
              'bg-gui-in/15   text-gui-in':   isLive,
              'bg-gui-out/15  text-gui-out':  isStarting,
              'bg-gui-dim/15  text-gui-dim':  !isLive && !isStarting,
            }"
          >
            {{ statusLabel }}
          </span>
        </div>

        <!-- Feed Area -->
        <div class="flex-1 relative min-h-0 overflow-hidden bg-[#0d0d0d]">

          <!-- LIVE: MJPEG stream -->
          <img
            v-if="isLive && hasRecentFrame"
            :src="faceStreamUrl"
            alt="Face Recognition Stream"
            class="w-full h-full object-contain"
            @error="onStreamError"
          />

          <!-- OFFLINE / STARTING / STALE -->
          <div v-else class="absolute inset-0 flex flex-col items-center justify-center">

            <svg
              class="absolute inset-0 w-full h-full pointer-events-none"
              viewBox="0 0 160 90"
              preserveAspectRatio="xMidYMid meet"
            >
              <defs>
                <mask id="face-oval-mask">
                  <rect width="160" height="90" fill="white"/>
                  <ellipse cx="80" cy="42.3" rx="26.1" ry="30.6" fill="black"/>
                </mask>
              </defs>
              <rect
                width="160" height="90"
                fill="rgba(0,0,0,0.62)"
                mask="url(#face-oval-mask)"
              />
              <ellipse
                cx="80" cy="42.3" rx="26.1" ry="30.6"
                fill="none"
                :stroke="ovalColor"
                stroke-width="0.5"
              />
              <ellipse
                cx="80" cy="42.3" rx="25.4" ry="29.9"
                fill="none"
                :stroke="ovalInnerColor"
                stroke-width="0.2"
              />
            </svg>

            <div
              class="absolute pointer-events-none z-10"
              style="bottom: 14px; left: 50%; transform: translateX(-50%)"
            >
              <div
                class="bg-[#f5f5f5] text-[#191919] text-xs font-medium
                       px-4 py-2 rounded shadow-lg whitespace-nowrap
                       border-l-[6px]"
                :style="{ borderColor: ovalColorHex }"
              >
                Place your face in the oval
              </div>
            </div>

            <div v-if="!isStarting" class="relative z-20 flex flex-col items-center gap-2">
              <button
                @click="startFace"
                class="px-6 py-2.5 rounded-lg text-sm font-semibold transition-colors
                       bg-gui-in/20 text-gui-in border border-gui-in/40
                       hover:bg-gui-in/30"
              >
                ▶ เปิด Face Recognition
              </button>
              <span class="text-xs text-gui-dim/60">main.py จะเริ่มรันบน Pi</span>
            </div>

            <div v-else class="relative z-20 flex items-center gap-2 text-gui-out text-sm">
              <div class="w-5 h-5 border-2 border-gui-out border-t-transparent rounded-full animate-spin"/>
              กำลังเริ่มต้น...
            </div>

            <div
              v-if="isLive && !hasRecentFrame"
              class="absolute top-4 left-1/2 -translate-x-1/2 z-20
                     bg-gui-out/15 border border-gui-out/40 text-gui-out
                     text-xs px-3 py-1.5 rounded-lg"
            >
              ⚠ Frame หาย — main.py อาจไม่ตอบสนอง
            </div>

          </div>

        </div>

        <!-- Controls -->
        <div class="px-4 py-3 border-t border-gui-border flex items-center gap-3 shrink-0 bg-gui-panel/80">
          <button
            @click="toggleFace"
            :disabled="isStarting"
            class="flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium
                   transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            :class="isLive
              ? 'bg-gui-fail/15 text-gui-fail border border-gui-fail/30 hover:bg-gui-fail/25'
              : 'bg-gui-in/15  text-gui-in  border border-gui-in/30  hover:bg-gui-in/25'"
          >
            <span>{{ isLive ? '⏹' : '▶' }}</span>
            {{ isStarting ? 'กำลังเริ่มต้น...' : isLive ? 'หยุด' : 'เปิด Face Recognition' }}
          </button>

          <span v-if="isLive && frameAge !== null" class="text-xs text-gui-dim">
            frame {{ frameAge }}s
          </span>

          <button
            @click="toggleFullscreen"
            class="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                   border border-gui-border text-gui-dim hover:text-gui-text
                   hover:border-gui-in/40 transition-colors"
            title="ขยายหน้าจอ (F)"
          >
            <span>⛶</span>
            {{ isFullscreen ? 'ย่อ' : 'ขยาย' }}
            <kbd class="text-[10px] opacity-50 bg-gui-border/30 px-1 rounded">F</kbd>
          </button>
        </div>

      </div>
      <!-- ── /กล้อง ─────────────────────────────────────────────── -->

      <!-- ── Right panel ────────────────────────────────────────────
           Normal mode : LiveDetection + สถานะระบบ + วิธีใช้
           Fullscreen  : รายชื่อวันนี้ (kiosk sidebar)
      ─────────────────────────────────────────────────────────────── -->
      <div
        :class="isFullscreen
          ? 'w-[340px] flex flex-col bg-gui-bg overflow-hidden'
          : 'space-y-4 flex flex-col'"
      >

        <!-- ─ Normal mode ─ -->
        <template v-if="!isFullscreen">

          <div class="bg-gui-panel border border-gui-border rounded-xl p-4 flex-1 overflow-y-auto"
               style="max-height: 420px">
            <LiveDetection />
          </div>

          <div class="bg-gui-panel border border-gui-border rounded-xl p-4 shrink-0">
            <h3 class="font-semibold text-sm mb-3 text-gui-dim">สถานะระบบ</h3>
            <div class="space-y-2.5 text-sm">

              <div class="flex items-center justify-between">
                <span class="text-gui-dim">Face Recognition</span>
                <span
                  class="font-medium"
                  :class="faceStatus.running ? 'text-gui-in' : 'text-gui-dim'"
                >
                  {{ faceStatus.running ? 'กำลังทำงาน' : 'หยุดทำงาน' }}
                </span>
              </div>

              <div v-if="faceStatus.pid" class="flex items-center justify-between">
                <span class="text-gui-dim">PID</span>
                <span class="font-mono text-xs text-gui-text">{{ faceStatus.pid }}</span>
              </div>

              <div class="flex items-center justify-between">
                <span class="text-gui-dim">Live Frame</span>
                <span
                  class="font-medium text-xs"
                  :class="hasRecentFrame ? 'text-gui-in' : 'text-gui-dim'"
                >
                  {{ hasRecentFrame ? `${frameAge}s ago` : 'ไม่มีข้อมูล' }}
                </span>
              </div>

            </div>
          </div>

          <div class="bg-gui-panel border border-gui-border rounded-xl p-4 shrink-0">
            <h3 class="font-semibold text-sm mb-3 text-gui-dim">วิธีใช้</h3>
            <ul class="text-xs text-gui-dim space-y-1.5 leading-relaxed">
              <li>• กด <span class="text-gui-in font-medium">▶ เปิด</span> เพื่อ start main.py</li>
              <li>• วางใบหน้าในกรอบวงรีเพื่อยืนยัน</li>
              <li>• Panel ขวาแสดงสถานะ liveness แบบ real-time</li>
              <li>• กด <span class="text-gui-fail font-medium">⏹ หยุด</span> เพื่อ stop main.py</li>
              <li>• หรือรัน <code class="bg-gui-border/30 px-1 rounded">python main.py</code> เอง</li>
            </ul>
          </div>

        </template>
        <!-- ─ /Normal mode ─ -->

        <!-- ─ Fullscreen mode: รายชื่อวันนี้ (kiosk sidebar) ──────── -->
        <template v-else>

          <!-- Header -->
          <div class="px-4 py-3 border-b border-gui-border bg-gui-panel flex items-center justify-between shrink-0">
            <div class="flex items-center gap-2">
              <span class="text-gui-in font-bold text-base">▣</span>
              <span class="font-semibold text-sm text-gui-text">รายชื่อวันนี้</span>
              <span class="text-xs px-2 py-0.5 rounded-full bg-gui-border/60 text-gui-dim font-mono tabular-nums">
                {{ mergedPersons.length }} คน
              </span>
            </div>
            <span v-if="!liveStale" class="flex items-center gap-1.5 text-xs text-gui-in font-semibold">
              <span class="w-1.5 h-1.5 rounded-full bg-gui-in animate-pulse" />
              LIVE
            </span>
            <span v-else class="text-xs text-gui-dim">offline</span>
          </div>

          <!-- Stats bar -->
          <div class="grid grid-cols-3 border-b border-gui-border shrink-0 bg-gui-panel/40">
            <div class="py-3 text-center border-r border-gui-border">
              <div class="text-xl font-bold text-gui-in tabular-nums">{{ stats.totalIn }}</div>
              <div class="text-[10px] text-gui-dim uppercase tracking-wider mt-0.5">เช็คอิน</div>
            </div>
            <div class="py-3 text-center border-r border-gui-border">
              <div class="text-xl font-bold text-gui-out tabular-nums">{{ stats.totalOut }}</div>
              <div class="text-[10px] text-gui-dim uppercase tracking-wider mt-0.5">เช็คเอาท์</div>
            </div>
            <div class="py-3 text-center">
              <div class="text-xl font-bold text-gui-text tabular-nums">{{ stats.currentlyIn }}</div>
              <div class="text-[10px] text-gui-dim uppercase tracking-wider mt-0.5">ยังอยู่</div>
            </div>
          </div>

          <!-- Legend -->
          <div class="flex items-center gap-3 px-4 py-1.5 border-b border-gui-border/40 shrink-0">
            <span class="flex items-center gap-1 text-[10px] text-gui-dim">
              <span class="w-1.5 h-1.5 rounded-full bg-gui-in" /> ยังอยู่
            </span>
            <span class="flex items-center gap-1 text-[10px] text-gui-dim">
              <span class="w-1.5 h-1.5 rounded-full bg-gui-out" /> ออกแล้ว
            </span>
            <span v-if="!liveStale" class="flex items-center gap-1 text-[10px] text-gui-dim">
              <span class="w-1.5 h-1.5 rounded-full bg-purple-400" /> กำลังตรวจ
            </span>
            <span class="ml-auto text-[10px] text-gui-dim/50 font-mono tabular-nums">IN&nbsp;&nbsp;&nbsp;OUT</span>
          </div>

          <!-- Person list (scrollable) -->
          <div class="flex-1 overflow-y-auto">

            <!-- Empty state -->
            <div
              v-if="mergedPersons.length === 0"
              class="flex flex-col items-center justify-center h-full gap-3 text-gui-dim"
            >
              <span class="text-4xl opacity-40">👁</span>
              <span class="text-sm">ยังไม่มีการลงเวลาวันนี้</span>
            </div>

            <!-- Person rows -->
            <div
              v-for="p in mergedPersons"
              :key="p.per_id"
              class="flex items-center gap-3 px-3 py-2.5 border-b border-gui-border/30
                     hover:bg-gui-panel/50 transition-colors relative"
            >
              <!-- Status bar (left edge 3px) -->
              <div
                class="absolute left-0 inset-y-0 w-[3px] rounded-r-sm"
                :class="p.status === 'IN'
                  ? 'bg-gui-in'
                  : p.status === 'PENDING'
                  ? 'bg-purple-400'
                  : 'bg-gui-out'"
              />

              <!-- Avatar / photo -->
              <div class="w-9 h-9 rounded-full overflow-hidden shrink-0 ml-1.5 ring-1"
                   :class="p.status === 'IN'
                     ? 'ring-gui-in/40'
                     : p.status === 'PENDING'
                     ? 'ring-purple-400/40'
                     : 'ring-gui-out/30'"
              >
                <img
                  v-if="!failedPhotos.has(p.per_id)"
                  :src="`${API_BASE}/person-face/${p.per_id}`"
                  class="w-full h-full object-cover"
                  @error="onPhotoFailed(p.per_id)"
                  alt=""
                />
                <div
                  v-else
                  class="w-full h-full flex items-center justify-center font-bold text-sm"
                  :class="p.status === 'IN'
                    ? 'bg-gui-in/20 text-gui-in'
                    : p.status === 'PENDING'
                    ? 'bg-purple-500/20 text-purple-400'
                    : 'bg-gui-out/20 text-gui-out'"
                >
                  {{ (p.per_name || p.name || '?')[0] }}
                </div>
              </div>

              <!-- Name + dept -->
              <div class="flex-1 min-w-0">
                <div class="text-sm font-medium text-gui-text truncate leading-snug">
                  {{ p.name || [p.per_name, p.per_surname].filter(Boolean).join(' ') || p.per_id }}
                </div>
                <div class="text-[11px] text-gui-dim truncate leading-snug">
                  {{ p.organize_th || p.posname_th || '\u00a0' }}
                </div>
              </div>

              <!-- Times (IN / OUT) -->
              <div class="text-right shrink-0">
                <div class="text-xs font-mono text-gui-in tabular-nums leading-snug">
                  {{ fmtTime(p.in_time) }}
                </div>
                <div
                  class="text-xs font-mono tabular-nums leading-snug"
                  :class="p.out_time ? 'text-gui-out' : 'text-gui-dim/30'"
                >
                  {{ p.out_time ? fmtTime(p.out_time) : '\u2014\u2014\u2014' }}
                </div>
              </div>

            </div>
          </div>
          <!-- /Person list -->

          <!-- Footer: วันที่ -->
          <div class="px-4 py-2 border-t border-gui-border shrink-0 text-center bg-gui-panel/30">
            <span class="text-[11px] text-gui-dim">
              {{ todayStr }}
            </span>
          </div>

        </template>
        <!-- ─ /Fullscreen mode ─ -->

      </div>
      <!-- ── /Right panel ────────────────────────────────────────── -->

    </div>
    <!-- ════ /FULLSCREEN WRAPPER ════════════════════════════════════ -->

    <!-- ══ แถบสถานะ refresh ════════════════════════════════════════ -->
    <div class="flex items-center justify-between gap-3 text-xs">
      <div class="flex items-center gap-2 text-gui-dim">
        <span
          class="w-2 h-2 rounded-full shrink-0"
          :class="attendError ? 'bg-gui-fail' : 'bg-gui-in animate-pulse-slow'"
        />
        <span v-if="attendError" class="text-gui-fail">เชื่อมต่อ API ไม่ได้: {{ attendError }}</span>
        <span v-else>อัพเดตเมื่อ {{ lastFetchStr }}</span>
      </div>

      <div class="flex items-center gap-2">
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

        <button
          @click="refresh"
          :disabled="attendLoading"
          class="px-3 py-1 rounded-lg border border-gui-border text-gui-dim
                 hover:border-gui-in/40 hover:text-gui-text transition-colors
                 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {{ attendLoading ? 'กำลังโหลด...' : '↻ Refresh' }}
        </button>
      </div>
    </div>

    <!-- ══ Confirm Dialog ════════════════════════════════════════════ -->
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

    <!-- ══ Stat Cards ════════════════════════════════════════════════ -->
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

    <!-- ══ Chart + Org ════════════════════════════════════════════════ -->
    <section class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="lg:col-span-2">
        <HourlyChart :hourly="hourly" />
      </div>
      <div>
        <OrgBreakdown :by-org="byOrg" />
      </div>
    </section>

    <!-- ══ Person Cards ══════════════════════════════════════════════ -->
    <section>
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold text-sm flex items-center gap-2">
          <span class="text-gui-in">▣</span>
          รายชื่อวันนี้
          <span class="text-xs text-gui-dim font-normal">({{ mergedPersons.length }} คน)</span>
          <span
            v-if="!liveStale"
            class="inline-flex items-center gap-1 text-xs px-1.5 py-0.5
                   rounded bg-gui-in/15 text-gui-in font-semibold"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-gui-in animate-pulse" />
            LIVE
          </span>
        </h2>
        <div class="flex items-center gap-3 text-xs text-gui-dim">
          <span class="flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-gui-in" /> ยังอยู่
          </span>
          <span class="flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-gui-out" /> ออกแล้ว
          </span>
          <span v-if="!liveStale" class="flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-purple-400" /> กำลังตรวจ
          </span>
        </div>
      </div>

      <div
        v-if="mergedPersons.length === 0"
        class="bg-gui-panel border border-gui-border rounded-xl
               py-12 flex flex-col items-center gap-2 text-gui-dim text-sm"
      >
        <span class="text-4xl">👁</span>
        {{ attendLoading ? 'กำลังโหลด...' : 'ยังไม่มีการลงเวลาวันนี้' }}
      </div>

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

    <!-- ══ Attendance Feed ════════════════════════════════════════════ -->
    <section style="min-height: 300px">
      <AttendanceFeed :feed="feed" :loading="attendLoading" />
    </section>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import LiveDetection  from '@/components/LiveDetection.vue'
import StatCard       from '@/components/StatCard.vue'
import PersonCard     from '@/components/PersonCard.vue'
import AttendanceFeed from '@/components/AttendanceFeed.vue'
import HourlyChart    from '@/components/HourlyChart.vue'
import OrgBreakdown   from '@/components/OrgBreakdown.vue'
import { useAttendance }  from '@/composables/useAttendance.js'
import { useLiveSession } from '@/composables/useLiveSession.js'

// ── Config ─────────────────────────────────────────────────────────
const BASE_URL         = import.meta.env.VITE_API_BASE_URL ?? '/api'
const FACE_STREAM_URL  = `${BASE_URL}/camera/face-stream`
const FACE_STATUS_URL  = `${BASE_URL}/camera/face/status`
const FACE_START_URL   = `${BASE_URL}/camera/face/start`
const FACE_STOP_URL    = `${BASE_URL}/camera/face/stop`
const API_BASE         = BASE_URL
const CLEAR_TODAY_URL  = `${API_BASE}/attendance/today/all`
const POLL_MS          = 2_000

// ── Camera State ───────────────────────────────────────────────────
const fullscreenWrapper = ref(null)   // fullscreen target (camera + sidebar)
const cameraContainer   = ref(null)   // ref ไว้ใช้ถ้าต้องการในอนาคต
const isFullscreen      = ref(false)
const faceStatus  = ref({ running: false, pid: null, has_frame: false, frame_age_sec: null })
const isStarting  = ref(false)
const streamError = ref(false)

const isLive = computed(() => faceStatus.value.running)

const hasRecentFrame = computed(() => {
  const age = faceStatus.value.frame_age_sec
  return age !== null && age <= 8
})

const frameAge = computed(() => faceStatus.value.frame_age_sec)

const statusLabel = computed(() => {
  if (isStarting.value) return 'กำลังเริ่มต้น...'
  if (isLive.value)     return hasRecentFrame.value ? 'LIVE' : 'รอ frame...'
  return 'ออฟไลน์'
})

const streamStartTs  = ref(Date.now())
const faceStreamUrl  = computed(() => `${FACE_STREAM_URL}?t=${streamStartTs.value}`)

const ovalColorHex   = computed(() => isLive.value ? '#00DC00' : '#d2d2d2')
const ovalColor      = computed(() => isLive.value ? 'rgba(0,220,0,0.9)' : 'rgba(210,210,210,0.8)')
const ovalInnerColor = computed(() =>
  isLive.value ? 'rgba(0,220,0,0.3)' : 'rgba(255,255,255,0.15)'
)

function toggleFace() {
  if (isLive.value) stopFace()
  else startFace()
}

async function startFace() {
  if (isStarting.value) return
  isStarting.value = true
  streamError.value = false
  try {
    const res  = await fetch(FACE_START_URL, { method: 'POST' })
    const data = await res.json()
    if (data.ok) {
      streamStartTs.value = Date.now()
      setTimeout(fetchStatus, 2_000)
    }
  } catch { /* ignore */ } finally {
    isStarting.value = false
  }
}

async function stopFace() {
  try { await fetch(FACE_STOP_URL, { method: 'POST' }) } catch { /* ignore */ }
}

function onStreamError() { streamError.value = true }

// ── Fullscreen ─────────────────────────────────────────────────────
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    fullscreenWrapper.value?.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

function onKeyDown(e) {
  if ((e.key === 'f' || e.key === 'F') && !e.ctrlKey && !e.metaKey && !e.altKey) {
    const tag = document.activeElement?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return
    e.preventDefault()
    toggleFullscreen()
  }
}

async function fetchStatus() {
  try {
    const res = await fetch(FACE_STATUS_URL)
    if (!res.ok) return
    faceStatus.value = await res.json()
  } catch { /* ignore */ }
}

let pollTimer = null

onMounted(() => {
  fetchStatus()
  pollTimer = setInterval(fetchStatus, POLL_MS)
  window.addEventListener('keydown', onKeyDown)
  document.addEventListener('fullscreenchange', onFullscreenChange)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  window.removeEventListener('keydown', onKeyDown)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})

// ── Attendance Data ─────────────────────────────────────────────────
const {
  stats,
  byOrg,
  hourly,
  feed,
  persons,
  loading:    attendLoading,
  error:      attendError,
  lastFetch,
  refresh,
} = useAttendance()

const {
  stale:   liveStale,
  persons: livePersons,
} = useLiveSession()

const mergedPersons = computed(() => {
  if (liveStale.value) return persons.value

  const dbMap  = Object.fromEntries(persons.value.map(p => [p.per_id, p]))
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
    const aInLive = liveSet.has(a.per_id)
    const bInLive = liveSet.has(b.per_id)
    if (aInLive !== bInLive) return aInLive ? -1 : 1
    const ord = { IN: 0, PENDING: 1, OUT: 2 }
    if (a.status !== b.status)
      return (ord[a.status] ?? 3) - (ord[b.status] ?? 3)
    return new Date(a.in_time ?? 0) - new Date(b.in_time ?? 0)
  })
})

// ── Attendance sidebar helpers ──────────────────────────────────────
// photo error tracking — reactive Set (reassign เพื่อให้ Vue track ได้)
const failedPhotos = ref(new Set())
function onPhotoFailed(pid) {
  failedPhotos.value = new Set([...failedPhotos.value, pid])
}

// แสดงเวลาแบบ HH:MM
function fmtTime(iso) {
  if (!iso) return '——'
  return new Date(iso).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
}

// วันที่ปัจจุบันภาษาไทย
const todayStr = new Date().toLocaleDateString('th-TH', {
  year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
})

// ── Clear Today ────────────────────────────────────────────────────
const showConfirm = ref(false)
const clearing    = ref(false)

function confirmClearToday() { showConfirm.value = true }

async function doClearToday() {
  showConfirm.value = false
  clearing.value    = true
  try {
    await fetch(CLEAR_TODAY_URL, { method: 'DELETE' })
    await refresh()
  } catch { /* ignore */ } finally {
    clearing.value = false
  }
}

// ── Last fetch label ───────────────────────────────────────────────
const now = ref(new Date())
setInterval(() => { now.value = new Date() }, 5000)

const lastFetchStr = computed(() => {
  if (!lastFetch.value) return 'รอข้อมูล...'
  const diff = Math.floor((now.value - lastFetch.value) / 1000)
  if (diff < 60) return `${diff} วินาทีที่แล้ว`
  return `${Math.floor(diff / 60)} นาทีที่แล้ว`
})
</script>
