<template>
  <div class="p-4 md:p-6 max-w-screen-2xl mx-auto w-full space-y-4">

    <!-- ════ Header ════════════════════════════════════════════════════ -->
    <div class="flex items-center gap-3 flex-wrap">
      <RouterLink
        to="/"
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
               border border-gui-border text-gui-dim hover:text-gui-text
               hover:border-gui-in/40 transition-colors shrink-0"
      >
        ← กลับ
      </RouterLink>

      <div class="flex items-center gap-2 min-w-0">
        <span
          class="w-2.5 h-2.5 rounded-full shrink-0 transition-colors"
          :class="{
            'bg-gui-in animate-pulse': camLive && camHasFrame,
            'bg-gui-out animate-pulse': camStarting,
            'bg-gui-dim': !camLive && !camStarting,
          }"
        />
        <h1 class="font-bold text-base text-gui-text truncate">
          {{ camera?.name ?? camId }}
        </h1>
        <span
          class="text-xs px-2 py-0.5 rounded-full font-medium shrink-0"
          :class="{
            'bg-gui-in/15 text-gui-in':     camLive,
            'bg-gui-out/15 text-gui-out':   camStarting && !camLive,
            'bg-gui-dim/15 text-gui-dim':   !camLive && !camStarting,
          }"
        >
          {{ camLive ? 'LIVE' : camStarting ? 'กำลังเริ่มต้น...' : 'ออฟไลน์' }}
        </span>
      </div>

      <div class="ml-auto flex items-center gap-2">
        <!-- Start / Stop -->
        <button
          @click="toggleFace"
          :disabled="camStarting"
          class="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold
                 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          :class="camLive
            ? 'bg-gui-fail/15 text-gui-fail border border-gui-fail/30 hover:bg-gui-fail/25'
            : 'bg-gui-in/15  text-gui-in  border border-gui-in/30  hover:bg-gui-in/25'"
        >
          {{ camLive ? '⏹ หยุด' : '▶ เปิด' }}
        </button>

        <!-- Fullscreen -->
        <button
          @click="toggleFullscreen"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                 border border-gui-border text-gui-dim hover:text-gui-text
                 hover:border-gui-in/40 transition-colors"
          title="ขยายหน้าจอ (F)"
        >
          ⛶ {{ isFullscreen ? 'ย่อ' : 'ขยาย' }}
          <kbd class="text-[10px] opacity-50 bg-gui-border/30 px-1 rounded">F</kbd>
        </button>
      </div>
    </div>

    <!-- ════ FULLSCREEN WRAPPER ════════════════════════════════════════ -->
    <div
      :class="isFullscreen
        ? 'fixed inset-0 z-50 flex flex-row bg-[#0a0a0a] overflow-hidden'
        : 'grid grid-cols-1 lg:grid-cols-3 gap-4'"
      :style="isFullscreen ? undefined : 'min-height: 520px'"
    >

      <!-- ── กล้อง (ซ้าย) ─────────────────────────────────────────── -->
      <div
        class="bg-black flex flex-col overflow-hidden"
        :class="isFullscreen
          ? 'flex-1 border-r border-gui-border'
          : 'lg:col-span-2 rounded-xl border border-gui-border'"
        :style="isFullscreen ? undefined : 'min-height: 440px'"
      >

        <!-- Header -->
        <div class="px-4 py-3 border-b border-gui-border flex items-center justify-between shrink-0 bg-gui-panel">
          <h2 class="font-semibold text-sm flex items-center gap-2">
            <span
              class="w-2 h-2 rounded-full shrink-0"
              :class="{
                'bg-gui-in animate-pulse-slow': camLive && camHasFrame,
                'bg-gui-out animate-pulse':     camStarting,
                'bg-gui-dim':                   !camLive && !camStarting,
              }"
            />
            Face Recognition
          </h2>
          <span class="text-xs text-gui-dim">
            {{ camera?.source_type === 'rtsp' ? 'IP / RTSP' : 'USB' }}
          </span>
        </div>

        <!-- Stream Area -->
        <div class="flex-1 relative min-h-0 overflow-hidden bg-[#0d0d0d]">

          <!-- Label overlay -->
          <div
            class="absolute top-2 left-2 z-20 flex items-center gap-1.5
                   bg-black/60 px-2 py-0.5 rounded-full backdrop-blur-sm"
          >
            <span
              class="w-1.5 h-1.5 rounded-full shrink-0"
              :class="{
                'bg-gui-in animate-pulse': camLive,
                'bg-gui-out animate-pulse': camStarting,
                'bg-gui-dim': !camLive && !camStarting,
              }"
            />
            <span class="text-[10px] font-medium text-gui-dim">{{ camera?.name ?? camId }}</span>
            <span v-if="camLive && frameAge !== null" class="text-[10px] text-gui-dim/60">
              {{ frameAge }}s
            </span>
          </div>

          <!-- LIVE stream -->
          <img
            :key="`stream-${camId}-${camState.streamStartTs}`"
            v-if="camLive && camHasFrame"
            :src="faceStreamUrl"
            alt="Face Recognition Stream"
            class="w-full h-full object-contain"
            @error="onStreamError"
          />

          <!-- OFFLINE / STARTING -->
          <div v-else class="absolute inset-0 flex flex-col items-center justify-center">

            <svg
              class="absolute inset-0 w-full h-full pointer-events-none"
              viewBox="0 0 160 90"
              preserveAspectRatio="xMidYMid meet"
            >
              <defs>
                <mask id="oval-mask-single">
                  <rect width="160" height="90" fill="white"/>
                  <ellipse cx="80" cy="42.3" rx="26.1" ry="30.6" fill="black"/>
                </mask>
              </defs>
              <rect width="160" height="90" fill="rgba(0,0,0,0.62)" mask="url(#oval-mask-single)"/>
              <ellipse cx="80" cy="42.3" rx="26.1" ry="30.6" fill="none"
                :stroke="camLive ? 'rgba(0,220,0,0.9)' : 'rgba(210,210,210,0.8)'" stroke-width="0.5"/>
              <ellipse cx="80" cy="42.3" rx="25.4" ry="29.9" fill="none"
                :stroke="camLive ? 'rgba(0,220,0,0.3)' : 'rgba(255,255,255,0.15)'" stroke-width="0.2"/>
            </svg>

            <!-- ปุ่มเปิด: เฉพาะเมื่อกล้องดับสนิท ไม่รัน ไม่โหลด -->
            <div v-if="!camStarting && !camLive" class="relative z-20 flex flex-col items-center gap-2">
              <button
                @click="startFace"
                class="px-6 py-2.5 rounded-lg text-sm font-semibold transition-colors
                       bg-gui-in/20 text-gui-in border border-gui-in/40 hover:bg-gui-in/30"
              >
                ▶ เปิดกล้อง
              </button>
            </div>

            <!-- Downloading screen: แสดงตลอดจนกว่ากล้องจะมี frame จริง -->
            <div v-else class="relative z-20 flex flex-col items-center gap-3 w-full px-10">
              <span class="text-white/50 text-xs tracking-widest uppercase">Face Attendance System</span>
              <span class="text-blue-300/90 text-sm font-medium">กำลังดาวน์โหลด...</span>
              <div class="w-full max-w-[260px] h-[5px] bg-white/10 rounded-full overflow-hidden">
                <div class="h-full bg-green-400/80 rounded-full"
                     :style="`width:${camBootProgress}%;transition:width 0.8s ease`"/>
              </div>
              <span v-if="camBootMsg" class="text-white/35 text-xs text-center">{{ camBootMsg }}</span>
              <div class="flex items-center gap-2.5">
                <div v-for="i in 5" :key="i" class="w-2 h-2 rounded-full dl-dot-single"
                     :style="`animation-delay:${(i-1)*0.18}s`"/>
              </div>
            </div>

          </div>

        </div>
        <!-- /Stream Area -->

        <!-- Info bar -->
        <div class="px-4 py-2 border-t border-gui-border shrink-0 bg-gui-panel/80
                    flex items-center gap-4 text-xs text-gui-dim">
          <span v-if="camState.faceStatus.pid" class="font-mono">
            PID: {{ camState.faceStatus.pid }}
          </span>
          <span :class="camHasFrame ? 'text-gui-in' : 'text-gui-dim/40'">
            {{ camHasFrame ? `frame ${frameAge}s ago` : 'ไม่มี frame' }}
          </span>
          <span class="ml-auto text-gui-dim/50">
            {{ camera?.source_type === 'rtsp' ? 'RTSP / IP' : 'USB' }}
          </span>
        </div>

      </div>
      <!-- ── /กล้อง ─────────────────────────────────────────────────── -->

      <!-- ── Right Panel ─────────────────────────────────────────────── -->
      <div
        :class="isFullscreen
          ? 'w-[340px] flex flex-col bg-gui-bg overflow-hidden'
          : 'space-y-4 flex flex-col'"
      >

        <!-- ─ Normal mode ─ -->
        <template v-if="!isFullscreen">

          <!-- Live Detection -->
          <div class="bg-gui-panel border border-gui-border rounded-xl p-4 flex-1 overflow-y-auto"
               style="max-height: 420px">
            <LiveDetection />
          </div>

          <!-- System status for this camera -->
          <div class="bg-gui-panel border border-gui-border rounded-xl p-4 shrink-0">
            <h3 class="font-semibold text-sm mb-3 text-gui-dim">สถานะกล้อง</h3>
            <div class="space-y-2 text-sm">
              <div class="flex items-center justify-between">
                <span class="text-gui-dim text-xs">สถานะ</span>
                <span class="text-xs font-medium"
                  :class="camState.faceStatus.running ? 'text-gui-in' : 'text-gui-dim'">
                  {{ camState.faceStatus.running ? 'กำลังทำงาน' : 'หยุดทำงาน' }}
                </span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-gui-dim text-xs">ประเภท</span>
                <span class="text-xs text-gui-text/70">
                  {{ camera?.source_type === 'rtsp' ? 'IP / RTSP' : 'USB' }}
                </span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-gui-dim text-xs">Frame ล่าสุด</span>
                <span class="text-xs font-mono"
                  :class="camHasFrame ? 'text-gui-in' : 'text-gui-dim/40'">
                  {{ camHasFrame ? `${frameAge}s ago` : '—' }}
                </span>
              </div>
              <div v-if="camState.faceStatus.pid" class="flex items-center justify-between">
                <span class="text-gui-dim text-xs">PID</span>
                <span class="font-mono text-xs text-gui-text/40">{{ camState.faceStatus.pid }}</span>
              </div>
            </div>
          </div>

          <!-- วิธีใช้ -->
          <div class="bg-gui-panel border border-gui-border rounded-xl p-4 shrink-0">
            <h3 class="font-semibold text-sm mb-3 text-gui-dim">วิธีใช้</h3>
            <ul class="text-xs text-gui-dim space-y-1.5 leading-relaxed">
              <li>• กด <span class="text-gui-in font-medium">▶ เปิด</span> เพื่อเริ่ม Face Recognition</li>
              <li>• กด <span class="text-gui-fail font-medium">⏹ หยุด</span> เพื่อหยุดกล้อง</li>
              <li>• กด <kbd class="bg-gui-border/30 px-1 rounded text-[10px]">F</kbd> เพื่อ Fullscreen</li>
              <li>• กด <span class="text-gui-dim font-medium">← กลับ</span> เพื่อกลับหน้าหลัก</li>
            </ul>
          </div>

        </template>

        <!-- ─ Fullscreen mode: kiosk sidebar ───────────────────────── -->
        <template v-else>

          <div class="px-4 py-3 border-b border-gui-border bg-gui-panel flex items-center justify-between shrink-0">
            <div class="flex items-center gap-2">
              <span class="text-gui-in font-bold text-base">▣</span>
              <span class="font-semibold text-sm text-gui-text">{{ camera?.name }}</span>
            </div>
            <span v-if="camLive" class="flex items-center gap-1.5 text-xs text-gui-in font-semibold">
              <span class="w-1.5 h-1.5 rounded-full bg-gui-in animate-pulse" />
              LIVE
            </span>
            <span v-else class="text-xs text-gui-dim">offline</span>
          </div>

          <!-- Live Detection in fullscreen -->
          <div class="flex-1 overflow-y-auto p-4">
            <LiveDetection />
          </div>

          <div class="px-4 py-2 border-t border-gui-border shrink-0 text-center bg-gui-panel/30">
            <span class="text-[11px] text-gui-dim">{{ todayStr }}</span>
          </div>

        </template>

      </div>
      <!-- ── /Right Panel ───────────────────────────────────────────── -->

    </div>
    <!-- ════ /FULLSCREEN WRAPPER ════════════════════════════════════════ -->

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute }    from 'vue-router'
import LiveDetection   from '@/components/LiveDetection.vue'
import { apiFetch, apiPost, streamUrl } from '@/api/attendance.js'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

// ── Route param ──────────────────────────────────────────────────────
const route = useRoute()
const camId = computed(() => route.params.camId)

// ── Camera info ──────────────────────────────────────────────────────
const camera = ref(null)

async function loadCamera() {
  try {
    const list = await apiFetch('/cameras')
    camera.value = list.find(c => c.id === camId.value) ?? null
  } catch { /* ignore */ }
}

// ── Camera State ─────────────────────────────────────────────────────
const camState = ref({
  faceStatus:    { running: false, pid: null, has_frame: false, frame_age_sec: null },
  isStarting:    false,
  isBooting:     false,
  bootMsg:       null,
  streamStartTs: Date.now(),
  streamError:   false,
})

const camLive     = computed(() => camState.value.faceStatus.running ?? false)
const camHasFrame = computed(() => {
  const age = camState.value.faceStatus.frame_age_sec
  return age !== null && age !== undefined && age <= 8
})
const frameAge    = computed(() => camState.value.faceStatus.frame_age_sec ?? null)
const camStarting = computed(() => camState.value.isStarting || camState.value.isBooting)
const camBootMsg  = computed(() => camState.value.bootMsg)

const _BOOT_STEPS = {
  'กำลังโหลดฐานข้อมูลใบหน้า...':        20,
  'กำลังโหลด AI Model (InsightFace)...': 50,
  'กำลังเปิดกล้อง...':                   75,
  'กำลังติดตั้งระบบตรวจจับ...':          90,
}
const camBootProgress = computed(() => {
  if (!camState.value.isBooting) return 100
  return _BOOT_STEPS[camState.value.bootMsg] ?? 5
})
const faceStreamUrl = computed(() =>
  streamUrl(`/cameras/${camId.value}/face-stream?t=${camState.value.streamStartTs}`)
)

// ── Actions ───────────────────────────────────────────────────────────
function toggleFace() {
  if (camLive.value) stopFace()
  else startFace()
}

async function startFace() {
  if (camState.value.isStarting || camState.value.isBooting) return
  camState.value.isStarting  = true
  camState.value.isBooting   = true
  camState.value.bootMsg     = null
  camState.value.streamError = false
  try {
    const data = await apiPost(`/cameras/${camId.value}/face/start`)
    if (data.ok) {
      camState.value.streamStartTs = Date.now()
      setTimeout(() => fetchStatus(), 2_000)
    } else {
      camState.value.isBooting = false
    }
  } catch { camState.value.isBooting = false } finally {
    camState.value.isStarting = false
  }
}

async function stopFace() {
  try {
    await apiPost(`/cameras/${camId.value}/face/stop`)
  } catch { /* ignore */ }
}

function onStreamError() {
  camState.value.streamError = true
}

// ── Status Polling ────────────────────────────────────────────────────
async function fetchStatus() {
  try {
    const data = await apiFetch(`/cameras/${camId.value}/face/status`)
    camState.value.faceStatus = data
    camState.value.bootMsg    = data.boot_msg ?? null
    if (data.has_frame || !data.running) camState.value.isBooting = false
  } catch { /* ignore */ }
}

let pollTimer = null

// ── Fullscreen (CSS pseudo-fullscreen — ไม่ใช้ native browser API) ──────
const isFullscreen = ref(false)

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

watch(isFullscreen, (val) => {
  document.body.style.overflow = val ? 'hidden' : ''
})

function onKeyDown(e) {
  if ((e.key === 'f' || e.key === 'F') && !e.ctrlKey && !e.metaKey && !e.altKey) {
    const tag = document.activeElement?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return
    e.preventDefault()
    toggleFullscreen()
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────
onMounted(async () => {
  await loadCamera()
  fetchStatus()
  pollTimer = setInterval(fetchStatus, 2_000)
  window.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  window.removeEventListener('keydown', onKeyDown)
  document.body.style.overflow = ''
})

// ── Date ──────────────────────────────────────────────────────────────
const todayStr = new Date().toLocaleDateString('th-TH', {
  year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
})
</script>

<style scoped>
@keyframes dl-dot-single {
  0%, 100% { opacity: 0.2; transform: scale(0.7); background: rgba(255,255,255,0.2); }
  50%       { opacity: 1;   transform: scale(1.3); background: rgba(100,210,255,0.9); }
}
.dl-dot-single {
  background: rgba(255,255,255,0.2);
  animation: dl-dot-single 1.2s ease-in-out infinite;
}
</style>
