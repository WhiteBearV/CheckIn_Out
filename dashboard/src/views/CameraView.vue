<template>
  <div class="p-4 md:p-6 max-w-screen-2xl mx-auto w-full space-y-4">

    <!-- ════ FULLSCREEN WRAPPER ════════════════════════════════════════ -->
    <div
      :class="isFullscreen
        ? 'fixed inset-0 z-50 flex flex-row bg-[#0a0a0a] overflow-hidden'
        : 'grid grid-cols-1 lg:grid-cols-3 gap-4'"
      :style="isFullscreen ? undefined : 'min-height: 520px'"
    >

      <!-- ── กล้อง (ซ้าย): ทุกกล้องใน box เดียว ─────────────────────── -->
      <!-- min-height ป้องกัน height collapse ระหว่าง right panel v-if/v-else switch -->
      <div
        class="bg-black flex flex-col overflow-hidden"
        :class="isFullscreen
          ? 'flex-1 border-r border-gui-border'
          : 'lg:col-span-2 rounded-xl border border-gui-border'"
        :style="isFullscreen ? undefined : 'min-height: 440px'"
      >

        <!-- Header: สถานะรวมทุกกล้อง -->
        <div class="px-4 py-3 border-b border-gui-border flex items-center justify-between shrink-0 bg-gui-panel">
          <h2 class="font-semibold text-sm flex items-center gap-2">
            <span
              class="w-2 h-2 rounded-full shrink-0 transition-colors"
              :class="{
                'bg-gui-in animate-pulse-slow': allLive,
                'bg-gui-out animate-pulse':     anyStarting,
                'bg-yellow-400 animate-pulse':  anyLive && !allLive,
                'bg-gui-dim':                   !anyLive && !anyStarting,
              }"
            />
            Face Recognition
            <span class="text-[10px] font-normal text-gui-dim/60">
              {{ cameras.length }} กล้อง
            </span>
          </h2>
          <span
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="{
              'bg-gui-in/15  text-gui-in':     allLive,
              'bg-yellow-400/15 text-yellow-400': anyLive && !allLive,
              'bg-gui-out/15 text-gui-out':    anyStarting && !anyLive,
              'bg-gui-dim/15 text-gui-dim':    !anyLive && !anyStarting,
            }"
          >
            {{ overallStatus }}
          </span>
        </div>

        <!-- ══════════════════════════════════════════════════════════════
             Feed Area — CSS absolute layout (img ทุกตัวอยู่ใน DOM เสมอ)
             ไม่ใช้ v-if/v-else เพื่อป้องกัน MJPEG ขาด connection
             ════════════════════════════════════════════════════════════ -->
        <div class="flex-1 relative overflow-hidden" style="min-height: 320px">
          <div class="absolute inset-0">

            <div
              v-for="(cam, camIdx) in cameras"
              :key="cam.id"
              class="absolute overflow-hidden bg-[#0d0d0d] transition-[top,bottom,left,right,width,height] duration-300 ease-in-out"
              :class="isThumbnail(cam.id) ? 'cursor-pointer group' : (!focusedCamId ? 'cursor-pointer group' : '')"
              :style="cameraStyle(cam.id)"
              @click="onCameraClick(cam.id)"
              :title="isThumbnail(cam.id) ? `คลิกเพื่อขยาย ${cam.name}` : (!focusedCamId ? `คลิกเพื่อขยาย ${cam.name}` : '')"
            >

              <!-- ─ เส้นคั่นระหว่างกล้อง (normal mode) ─ -->
              <div v-if="camIdx > 0 && !focusedCamId"
                   class="absolute left-0 inset-y-0 w-px bg-gui-border/50 z-30 pointer-events-none" />

              <!-- ─ Label + mini status (top-left) ─ -->
              <div class="absolute top-2 left-2 z-20 flex items-center gap-1.5
                           bg-black/60 px-2 py-0.5 rounded-full backdrop-blur-sm pointer-events-none">
                <span class="w-1.5 h-1.5 rounded-full shrink-0"
                  :class="{
                    'bg-gui-in animate-pulse':  isLive(cam.id),
                    'bg-gui-out animate-pulse':  getCamState(cam.id).isStarting,
                    'bg-gui-dim':               !isLive(cam.id) && !getCamState(cam.id).isStarting,
                  }" />
                <span class="text-[10px] font-medium"
                  :class="isThumbnail(cam.id) ? 'text-white/70' : 'text-gui-dim'">{{ cam.name }}</span>
              </div>

              <!-- ─ Top-right: ✕ (focused) | ⛶เต็มจอ (normal) | (ไม่มีบน thumbnail) ─ -->
              <button v-if="focusedCamId && cam.id === focusedCamId"
                @click.stop="focusedCamId = null"
                class="absolute top-2 right-2 z-20 flex items-center gap-1
                       bg-black/60 px-2 py-0.5 rounded-full backdrop-blur-sm
                       text-[10px] text-gui-dim hover:text-gui-text hover:bg-black/80 transition-colors"
                title="ย่อกลับโหมดปกติ"
              >✕ <span class="hidden sm:inline">ย่อลง</span></button>

              <RouterLink v-else-if="!focusedCamId"
                :to="{ name: 'camera-detail', params: { camId: cam.id } }"
                class="absolute top-2 right-2 z-20 flex items-center gap-1
                       bg-black/60 px-2 py-0.5 rounded-full backdrop-blur-sm
                       text-[10px] text-gui-dim hover:text-gui-text hover:bg-black/80 transition-colors"
                title="ดูหน้าเต็มของกล้องนี้ (หน้าใหม่)"
                @click.stop
              >⛶ <span class="hidden sm:inline">เต็มจอ</span></RouterLink>

              <!-- ─ Hover highlight ─ -->
              <div class="absolute inset-0 bg-gui-in/0 group-hover:bg-gui-in/8 transition-colors pointer-events-none z-10" />
              <div v-if="isThumbnail(cam.id)"
                   class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20">
                <span class="bg-black/70 text-white text-[9px] px-2 py-0.5 rounded-full">ขยาย ⛶</span>
              </div>

              <!-- ─ LIVE stream (v-if บน img เท่านั้น, ไม่กระทบ sibling img) ─ -->
              <img
                :key="`stream-${cam.id}-${getCamState(cam.id).streamStartTs}`"
                v-if="isLive(cam.id) && hasRecentFrame(cam.id)"
                :src="streamUrlFor(cam.id)"
                alt="Face Recognition Stream"
                class="w-full h-full object-contain"
                @error="() => onStreamError(cam.id)"
              />

              <!-- ─ OFFLINE / STARTING ─ -->
              <div v-else class="absolute inset-0 flex flex-col items-center justify-center z-10">

                <!-- Oval guide (ซ่อนบน thumbnail) -->
                <svg v-if="!isThumbnail(cam.id)"
                  class="absolute inset-0 w-full h-full pointer-events-none"
                  viewBox="0 0 160 90" preserveAspectRatio="xMidYMid meet"
                >
                  <defs>
                    <mask :id="`oval-mask-${cam.id}`">
                      <rect width="160" height="90" fill="white"/>
                      <ellipse cx="80" cy="42.3" rx="26.1" ry="30.6" fill="black"/>
                    </mask>
                  </defs>
                  <rect width="160" height="90" fill="rgba(0,0,0,0.62)" :mask="`url(#oval-mask-${cam.id})`"/>
                  <ellipse cx="80" cy="42.3" rx="26.1" ry="30.6" fill="none" :stroke="ovalColorFor(cam.id)" stroke-width="0.5"/>
                  <ellipse cx="80" cy="42.3" rx="25.4" ry="29.9" fill="none" :stroke="ovalInnerColorFor(cam.id)" stroke-width="0.2"/>
                </svg>

                <!-- Thumbnail offline: แสดงแค่ข้อความ -->
                <div v-if="isThumbnail(cam.id)" class="relative z-20 text-[9px] text-gui-dim/70">
                  {{ getCamState(cam.id).isStarting ? 'กำลังเริ่ม...' : 'ออฟไลน์' }}
                </div>

                <!-- Normal/focused offline: ปุ่มเปิด -->
                <template v-else>
                  <div v-if="!getCamState(cam.id).isStarting" class="relative z-20 flex flex-col items-center gap-2">
                    <button @click.stop="startFace(cam.id)"
                      class="px-5 py-2 rounded-lg text-xs font-semibold transition-colors
                             bg-gui-in/20 text-gui-in border border-gui-in/40 hover:bg-gui-in/30"
                    >▶ เปิด</button>
                  </div>
                  <div v-else class="relative z-20 flex items-center gap-2 text-gui-out text-xs">
                    <div class="w-4 h-4 border-2 border-gui-out border-t-transparent rounded-full animate-spin"/>
                    กำลังเริ่มต้น...
                  </div>
                  <div v-if="isLive(cam.id) && !hasRecentFrame(cam.id)"
                    class="absolute top-4 left-1/2 -translate-x-1/2 z-20
                           bg-gui-out/15 border border-gui-out/40 text-gui-out text-xs px-3 py-1.5 rounded-lg"
                  >⚠ Frame หาย</div>
                </template>

              </div>

            </div>

          </div>
        </div>
        <!-- /Feed Area -->

        <!-- Controls: per-camera toggles + fullscreen -->
        <div class="px-4 py-3 border-t border-gui-border flex items-center gap-3 shrink-0 bg-gui-panel/80 flex-wrap">

          <!-- Per-camera start/stop buttons -->
          <template v-for="cam in cameras" :key="`ctrl-${cam.id}`">
            <button
              @click="toggleFace(cam.id)"
              :disabled="getCamState(cam.id).isStarting"
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                     transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              :class="isLive(cam.id)
                ? 'bg-gui-fail/15 text-gui-fail border border-gui-fail/30 hover:bg-gui-fail/25'
                : 'bg-gui-in/15  text-gui-in  border border-gui-in/30  hover:bg-gui-in/25'"
            >
              <span>{{ isLive(cam.id) ? '⏹' : '▶' }}</span>
              <span class="hidden sm:inline">{{ cam.name }}</span>
              <span class="sm:hidden">{{ cam.id }}</span>
              <span v-if="isLive(cam.id) && frameAgeFor(cam.id) !== null"
                class="text-[10px] opacity-70">{{ frameAgeFor(cam.id) }}s</span>
            </button>
          </template>

          <!-- Start/Stop all -->
          <button
            v-if="cameras.length > 1"
            @click="anyLive ? stopAll() : startAll()"
            :disabled="anyStarting"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                   border transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            :class="anyLive
              ? 'bg-gui-fail/10 text-gui-fail/80 border-gui-fail/20 hover:bg-gui-fail/20'
              : 'bg-gui-in/10   text-gui-in/80  border-gui-in/20   hover:bg-gui-in/20'"
          >
            {{ anyLive ? '⏹ หยุดทั้งหมด' : '▶ เปิดทั้งหมด' }}
          </button>

          <button
            @click="showCameraManager = true"
            class="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                   border border-gui-border text-gui-dim hover:text-gui-text
                   hover:border-gui-in/40 transition-colors"
            title="จัดการกล้อง"
          >
            ⚙ จัดการกล้อง
          </button>

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
            <div class="space-y-3 text-sm">
              <div
                v-for="cam in cameras"
                :key="`status-${cam.id}`"
                class="pb-2.5 border-b border-gui-border/30 last:border-0 last:pb-0"
              >
                <div class="flex items-center justify-between">
                  <span class="text-gui-dim text-xs font-medium">{{ cam.name }}</span>
                  <span
                    class="text-xs font-medium"
                    :class="getCamState(cam.id).faceStatus.running ? 'text-gui-in' : 'text-gui-dim'"
                  >
                    {{ getCamState(cam.id).faceStatus.running ? 'กำลังทำงาน' : 'หยุดทำงาน' }}
                  </span>
                </div>
                <div class="flex items-center justify-between mt-1">
                  <span class="text-gui-dim/50 text-[11px]">
                    {{ cam.source_type === 'rtsp' ? 'IP / RTSP' : 'USB' }}
                  </span>
                  <span
                    class="text-[11px]"
                    :class="hasRecentFrame(cam.id) ? 'text-gui-in' : 'text-gui-dim/40'"
                  >
                    {{ hasRecentFrame(cam.id) ? `frame ${frameAgeFor(cam.id)}s ago` : '—' }}
                  </span>
                </div>
                <div v-if="getCamState(cam.id).faceStatus.pid" class="flex items-center justify-between mt-1">
                  <span class="text-gui-dim/40 text-[11px]">PID</span>
                  <span class="font-mono text-[11px] text-gui-text/40">{{ getCamState(cam.id).faceStatus.pid }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="bg-gui-panel border border-gui-border rounded-xl p-4 shrink-0">
            <h3 class="font-semibold text-sm mb-3 text-gui-dim">วิธีใช้</h3>
            <ul class="text-xs text-gui-dim space-y-1.5 leading-relaxed">
              <li>• กด <span class="text-gui-in font-medium">▶ ชื่อกล้อง</span> เพื่อ start กล้องนั้น</li>
              <li>• กด <span class="text-gui-in font-medium">▶ เปิดทั้งหมด</span> เพื่อ start พร้อมกัน</li>
              <li>• แต่ละกล้องรัน main.py แยกกัน พร้อมกันได้</li>
              <li>• Panel ขวาแสดงสถานะ liveness แบบ real-time</li>
            </ul>
          </div>

        </template>

        <!-- ─ Fullscreen mode: รายชื่อวันนี้ (kiosk sidebar) ──────── -->
        <template v-else>

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

          <div class="flex-1 overflow-y-auto">
            <div v-if="mergedPersons.length === 0"
              class="flex flex-col items-center justify-center h-full gap-3 text-gui-dim">
              <span class="text-4xl opacity-40">👁</span>
              <span class="text-sm">ยังไม่มีการลงเวลาวันนี้</span>
            </div>

            <div
              v-for="p in mergedPersons" :key="p.per_id"
              class="flex items-center gap-3 px-3 py-2.5 border-b border-gui-border/30
                     hover:bg-gui-panel/50 transition-colors relative"
            >
              <div class="absolute left-0 inset-y-0 w-[3px] rounded-r-sm"
                :class="p.status==='IN' ? 'bg-gui-in' : p.status==='PENDING' ? 'bg-purple-400' : 'bg-gui-out'"/>

              <div class="w-9 h-9 rounded-full overflow-hidden shrink-0 ml-1.5 ring-1"
                :class="p.status==='IN' ? 'ring-gui-in/40' : p.status==='PENDING' ? 'ring-purple-400/40' : 'ring-gui-out/30'">
                <img v-if="!failedPhotos.has(p.per_id)" :src="photoSrc(p.per_id)"
                  class="w-full h-full object-cover" @error="onPhotoFailed(p.per_id)" alt=""/>
                <div v-else class="w-full h-full flex items-center justify-center font-bold text-sm"
                  :class="p.status==='IN' ? 'bg-gui-in/20 text-gui-in' : p.status==='PENDING' ? 'bg-purple-500/20 text-purple-400' : 'bg-gui-out/20 text-gui-out'">
                  {{ (p.per_name || p.name || '?')[0] }}
                </div>
              </div>

              <div class="flex-1 min-w-0">
                <div class="text-sm font-medium text-gui-text truncate leading-snug">
                  {{ p.name || [p.per_name, p.per_surname].filter(Boolean).join(' ') || p.per_id }}
                </div>
                <div class="text-[11px] text-gui-dim truncate leading-snug">
                  {{ p.organize_th || p.posname_th || '\u00a0' }}
                </div>
              </div>

              <div class="text-right shrink-0">
                <div class="text-xs font-mono text-gui-in tabular-nums leading-snug">{{ fmtTime(p.in_time) }}</div>
                <div class="text-xs font-mono tabular-nums leading-snug"
                  :class="p.out_time ? 'text-gui-out' : 'text-gui-dim/30'">
                  {{ p.out_time ? fmtTime(p.out_time) : '\u2014\u2014\u2014' }}
                </div>
              </div>
            </div>
          </div>

          <div class="px-4 py-2 border-t border-gui-border shrink-0 text-center bg-gui-panel/30">
            <span class="text-[11px] text-gui-dim">{{ todayStr }}</span>
          </div>

        </template>

      </div>
      <!-- ── /Right panel ────────────────────────────────────────── -->

    </div>
    <!-- ════ /FULLSCREEN WRAPPER ════════════════════════════════════ -->

    <!-- ══ แถบสถานะ refresh ════════════════════════════════════════ -->
    <div class="flex items-center justify-between gap-3 text-xs">
      <div class="flex items-center gap-2 text-gui-dim">
        <span class="w-2 h-2 rounded-full shrink-0"
          :class="attendError ? 'bg-gui-fail' : 'bg-gui-in animate-pulse-slow'"/>
        <span v-if="attendError" class="text-gui-fail">เชื่อมต่อ API ไม่ได้: {{ attendError }}</span>
        <span v-else>อัพเดตเมื่อ {{ lastFetchStr }}</span>
      </div>
      <div class="flex items-center gap-2">
        <button @click="confirmClearToday" :disabled="clearing"
          class="px-3 py-1 rounded-lg border border-gui-fail/30 text-gui-fail/70
                 hover:border-gui-fail/60 hover:text-gui-fail transition-colors
                 disabled:opacity-40 disabled:cursor-not-allowed">
          {{ clearing ? 'กำลังล้าง...' : '🗑 Clear Today' }}
        </button>
        <button @click="refresh" :disabled="attendLoading"
          class="px-3 py-1 rounded-lg border border-gui-border text-gui-dim
                 hover:border-gui-in/40 hover:text-gui-text transition-colors
                 disabled:opacity-40 disabled:cursor-not-allowed">
          {{ attendLoading ? 'กำลังโหลด...' : '↻ Refresh' }}
        </button>
      </div>
    </div>

    <!-- ══ Camera Manager Modal ══════════════════════════════════════ -->
    <CameraManagerModal
      v-if="showCameraManager"
      :cameras="cameras"
      :api-base="API_BASE"
      @close="showCameraManager = false"
      @changed="onCamerasChanged"
    />

    <!-- ══ Confirm Dialog ════════════════════════════════════════════ -->
    <Teleport to="body">
      <div v-if="showConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        @click.self="showConfirm = false">
        <div class="bg-gui-panel border border-gui-fail/40 rounded-2xl shadow-2xl p-6 w-full max-w-sm mx-4">
          <h3 class="font-bold text-base mb-1 text-gui-text">ยืนยันการล้างข้อมูล</h3>
          <p class="text-sm text-gui-dim mb-1">
            จะ<span class="text-gui-fail font-semibold">ลบข้อมูลการลงเวลาวันนี้ทั้งหมด</span>
            ออกจาก database และล้าง session cache
          </p>
          <p class="text-xs text-gui-dim/70 mb-5">⚠ ใช้สำหรับ testing เท่านั้น</p>
          <div class="flex gap-3 justify-end">
            <button @click="showConfirm = false"
              class="px-4 py-1.5 rounded-lg text-sm border border-gui-border text-gui-dim hover:text-gui-text transition-colors">
              ยกเลิก
            </button>
            <button @click="doClearToday"
              class="px-4 py-1.5 rounded-lg text-sm font-semibold bg-gui-fail/15 text-gui-fail border border-gui-fail/40 hover:bg-gui-fail/25 transition-colors">
              ยืนยัน ล้างข้อมูล
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ══ Stat Cards ════════════════════════════════════════════════ -->
    <section class="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
      <StatCard label="เช็คอินวันนี้"        :value="stats.totalIn"      icon="✅" color="green"  sub-label="จำนวนครั้ง IN ทั้งหมด"/>
      <StatCard label="เช็คเอาท์วันนี้"      :value="stats.totalOut"     icon="🚪" color="yellow" sub-label="จำนวนครั้ง OUT ทั้งหมด"/>
      <StatCard label="ยังอยู่ในที่ทำงาน"    :value="stats.currentlyIn"  icon="👥" color="blue"   sub-label="IN แต่ยังไม่มี OUT วันนี้"/>
      <StatCard label="พนักงานทั้งหมดวันนี้" :value="persons.length"     icon="🏢" color="red"    sub-label="จำนวนคน (ไม่นับซ้ำ)"/>
    </section>

    <!-- ══ Chart + Org ════════════════════════════════════════════════ -->
    <section class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="lg:col-span-2"><HourlyChart :hourly="hourly" /></div>
      <div><OrgBreakdown :by-org="byOrg" /></div>
    </section>

    <!-- ══ Person Cards ══════════════════════════════════════════════ -->
    <section>
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold text-sm flex items-center gap-2">
          <span class="text-gui-in">▣</span>
          รายชื่อวันนี้
          <span class="text-xs text-gui-dim font-normal">({{ mergedPersons.length }} คน)</span>
          <span v-if="!liveStale"
            class="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-gui-in/15 text-gui-in font-semibold">
            <span class="w-1.5 h-1.5 rounded-full bg-gui-in animate-pulse"/>LIVE
          </span>
        </h2>
        <div class="flex items-center gap-3 text-xs text-gui-dim">
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-gui-in"/> ยังอยู่</span>
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-gui-out"/> ออกแล้ว</span>
          <span v-if="!liveStale" class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-purple-400"/> กำลังตรวจ</span>
        </div>
      </div>
      <div v-if="mergedPersons.length === 0"
        class="bg-gui-panel border border-gui-border rounded-xl py-12 flex flex-col items-center gap-2 text-gui-dim text-sm">
        <span class="text-4xl">👁</span>
        {{ attendLoading ? 'กำลังโหลด...' : 'ยังไม่มีการลงเวลาวันนี้' }}
      </div>
      <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        <PersonCard v-for="p in mergedPersons" :key="p.per_id" :person="p" :api-base="API_BASE"/>
      </div>
    </section>

    <!-- ══ Attendance Feed ════════════════════════════════════════════ -->
    <section style="min-height: 300px">
      <AttendanceFeed :feed="feed" :loading="attendLoading"/>
    </section>

  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import LiveDetection       from '@/components/LiveDetection.vue'
import StatCard            from '@/components/StatCard.vue'
import PersonCard          from '@/components/PersonCard.vue'
import AttendanceFeed      from '@/components/AttendanceFeed.vue'
import HourlyChart         from '@/components/HourlyChart.vue'
import OrgBreakdown        from '@/components/OrgBreakdown.vue'
import CameraManagerModal  from '@/components/CameraManagerModal.vue'
import { useAttendance }  from '@/composables/useAttendance.js'
import { useLiveSession } from '@/composables/useLiveSession.js'

// ── Config ─────────────────────────────────────────────────────────
const BASE_URL        = import.meta.env.VITE_API_BASE_URL ?? '/api'
const API_BASE        = BASE_URL
const CLEAR_TODAY_URL = `${API_BASE}/attendance/today/all`
const POLL_MS         = 2_000

// ── Camera List ─────────────────────────────────────────────────────
const cameras = ref([])

async function loadCameras() {
  try {
    const res = await fetch(`${BASE_URL}/cameras`)
    if (res.ok) {
      cameras.value = await res.json()
      cameras.value.forEach(cam => initCamState(cam))
    }
  } catch { /* ignore */ }
}

// ── Camera Manager Modal ─────────────────────────────────────────────
const showCameraManager = ref(false)

async function onCamerasChanged() {
  // รีโหลดรายการกล้องหลังเพิ่ม/ลบ — reset focusedCamId ถ้ากล้องนั้นถูกลบ
  await loadCameras()
  if (focusedCamId.value && !cameras.value.find(c => c.id === focusedCamId.value)) {
    focusedCamId.value = null
  }
}

// ── Per-Camera State ─────────────────────────────────────────────────
// camStates[cam_id] = { faceStatus, isStarting, streamStartTs, streamError }
const camStates = reactive({})

function initCamState(cam) {
  if (!camStates[cam.id]) {
    camStates[cam.id] = {
      faceStatus:    { running: false, pid: null, has_frame: false, frame_age_sec: null },
      isStarting:    false,
      streamStartTs: Date.now(),
      streamError:   false,
    }
  }
}

function getCamState(camId) {
  return camStates[camId] ?? {
    faceStatus:    { running: false, pid: null, has_frame: false, frame_age_sec: null },
    isStarting:    false,
    streamStartTs: 0,
    streamError:   false,
  }
}

// ── Focus Mode (CSS absolute layout — img ไม่ถูก unmount เมื่อสลับ) ────────
const THUMB_H      = 140          // ความสูง thumbnail strip (px)
const focusedCamId = ref(null)

// คำนวณ style ของแต่ละกล้องตาม focusedCamId (ไม่มี DOM remove/add)
function cameraStyle(camId) {
  const n   = cameras.value.length
  const idx = cameras.value.findIndex(c => c.id === camId)
  if (n === 0) return ''

  if (focusedCamId.value) {
    const others = cameras.value.filter(c => c.id !== focusedCamId.value)
    if (camId === focusedCamId.value) {
      const hasThumb = others.length > 0
      return `top:0;left:0;right:0;bottom:${hasThumb ? THUMB_H : 0}px`
    } else {
      const tIdx = others.findIndex(c => c.id === camId)
      const tN   = others.length
      return `bottom:0;height:${THUMB_H}px;left:${((tIdx / tN) * 100).toFixed(3)}%;width:${(100 / tN).toFixed(3)}%`
    }
  }
  // Normal: แบ่งเท่ากัน
  return `top:0;bottom:0;left:${((idx / n) * 100).toFixed(3)}%;width:${(100 / n).toFixed(3)}%`
}

// กล้องนี้เป็น thumbnail หรือเปล่า
function isThumbnail(camId) {
  return !!focusedCamId.value && camId !== focusedCamId.value
}

// คลิกที่กล้อง
function onCameraClick(camId) {
  if (isThumbnail(camId)) {
    focusedCamId.value = camId   // สลับ focused
  } else if (!focusedCamId.value) {
    focusedCamId.value = camId   // เข้า focus mode
  }
  // คลิกที่ focused cam → ไม่ทำอะไร (ใช้ปุ่ม ✕ เพื่อออก)
}

// ── Per-Camera Helpers ───────────────────────────────────────────────
const isLive          = (camId) => getCamState(camId).faceStatus.running ?? false
const hasRecentFrame  = (camId) => {
  const age = getCamState(camId).faceStatus.frame_age_sec
  return age !== null && age !== undefined && age <= 8
}
const frameAgeFor     = (camId) => getCamState(camId).faceStatus.frame_age_sec ?? null
const streamUrlFor    = (camId) =>
  `${BASE_URL}/cameras/${camId}/face-stream?t=${getCamState(camId).streamStartTs}`
const ovalColorFor    = (camId) =>
  isLive(camId) ? 'rgba(0,220,0,0.9)' : 'rgba(210,210,210,0.8)'
const ovalInnerColorFor = (camId) =>
  isLive(camId) ? 'rgba(0,220,0,0.3)' : 'rgba(255,255,255,0.15)'

// ── Aggregate State ──────────────────────────────────────────────────
const anyLive     = computed(() => cameras.value.some(c => isLive(c.id)))
const allLive     = computed(() => cameras.value.length > 0 && cameras.value.every(c => isLive(c.id)))
const anyStarting = computed(() => cameras.value.some(c => getCamState(c.id).isStarting))
const overallStatus = computed(() => {
  if (anyStarting.value && !anyLive.value) return 'กำลังเริ่มต้น...'
  if (allLive.value) return 'LIVE'
  if (anyLive.value) return `LIVE (${cameras.value.filter(c => isLive(c.id)).length}/${cameras.value.length})`
  return 'ออฟไลน์'
})

// ── Camera Actions ───────────────────────────────────────────────────
function toggleFace(camId) {
  if (isLive(camId)) stopFace(camId)
  else startFace(camId)
}

async function startFace(camId) {
  if (!camStates[camId] || camStates[camId].isStarting) return
  camStates[camId].isStarting  = true
  camStates[camId].streamError = false
  try {
    const res  = await fetch(`${BASE_URL}/cameras/${camId}/face/start`, { method: 'POST' })
    const data = await res.json()
    if (data.ok) {
      camStates[camId].streamStartTs = Date.now()
      setTimeout(() => fetchStatus(camId), 2_000)
    }
  } catch { /* ignore */ } finally {
    camStates[camId].isStarting = false
  }
}

async function stopFace(camId) {
  try {
    await fetch(`${BASE_URL}/cameras/${camId}/face/stop`, { method: 'POST' })
  } catch { /* ignore */ }
}

async function startAll() {
  await Promise.all(cameras.value.map(cam => startFace(cam.id)))
}

async function stopAll() {
  await Promise.all(cameras.value.map(cam => stopFace(cam.id)))
}

function onStreamError(camId) {
  if (camStates[camId]) camStates[camId].streamError = true
}

// ── Status Polling ───────────────────────────────────────────────────
async function fetchStatus(camId) {
  try {
    const res = await fetch(`${BASE_URL}/cameras/${camId}/face/status`)
    if (!res.ok) return
    const data = await res.json()
    if (camStates[camId]) camStates[camId].faceStatus = data
  } catch { /* ignore */ }
}

async function fetchAllStatuses() {
  await Promise.all(cameras.value.map(cam => fetchStatus(cam.id)))
}

let pollTimer = null

// ── Fullscreen (CSS pseudo-fullscreen — ไม่ใช้ native browser API) ──────
// ใช้ fixed inset-0 z-50 แทน requestFullscreen เพื่อหลีกเลี่ยง MJPEG หลุด connection
const isFullscreen = ref(false)

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

watch(isFullscreen, (val) => {
  // ล็อก scroll เมื่อ fullscreen, คืนเมื่อย่อ
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

// ── Lifecycle ────────────────────────────────────────────────────────
onMounted(async () => {
  await loadCameras()
  fetchAllStatuses()
  pollTimer = setInterval(fetchAllStatuses, POLL_MS)
  window.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  window.removeEventListener('keydown', onKeyDown)
  document.body.style.overflow = '' // cleanup เผื่อ unmount ขณะ fullscreen
})

// ── Attendance Data ──────────────────────────────────────────────────
const {
  stats, byOrg, hourly, feed, persons,
  loading: attendLoading, error: attendError, lastFetch, refresh,
} = useAttendance()

const { stale: liveStale, persons: livePersons } = useLiveSession()

const mergedPersons = computed(() => {
  if (liveStale.value) return persons.value
  const dbMap   = Object.fromEntries(persons.value.map(p => [p.per_id, p]))
  const liveSet = new Set(livePersons.value.map(p => p.per_id))
  const result  = livePersons.value.map(lp => {
    const db = dbMap[lp.per_id]
    return {
      per_id: lp.per_id, name: lp.display_name || lp.per_id,
      prename_th: db?.prename_th || '', per_name: lp.per_name, per_surname: lp.per_surname,
      posname_th: lp.posname_th, organize_th: lp.organize_th,
      in_time: db?.in_time || lp.first_seen || null, out_time: db?.out_time || null,
      status: lp.checked_in ? (lp.checked_out ? 'OUT' : 'IN') : 'PENDING',
      liveness: lp.liveness, liveness_msg: lp.liveness_msg,
    }
  })
  persons.value.forEach(dbP => {
    if (!liveSet.has(dbP.per_id))
      result.push({ ...dbP, liveness: null, liveness_msg: null })
  })
  return result.sort((a, b) => {
    const aL = liveSet.has(a.per_id), bL = liveSet.has(b.per_id)
    if (aL !== bL) return aL ? -1 : 1
    const ord = { IN: 0, PENDING: 1, OUT: 2 }
    if (a.status !== b.status) return (ord[a.status] ?? 3) - (ord[b.status] ?? 3)
    return new Date(a.in_time ?? 0) - new Date(b.in_time ?? 0)
  })
})

// ── Photo helpers ────────────────────────────────────────────────────
const failedPhotos = ref(new Set())
const photoRetry   = ref(new Map())

function onPhotoFailed(pid) {
  failedPhotos.value = new Set([...failedPhotos.value, pid])
}

function photoSrc(pid) {
  const bust = photoRetry.value.get(pid)
  return bust ? `${API_BASE}/person-face/${pid}?t=${bust}` : `${API_BASE}/person-face/${pid}`
}

watch(mergedPersons, (persons) => {
  persons.forEach(p => {
    if (p.status === 'IN' && failedPhotos.value.has(p.per_id)) {
      const next = new Set(failedPhotos.value); next.delete(p.per_id); failedPhotos.value = next
      const m = new Map(photoRetry.value); m.set(p.per_id, Date.now()); photoRetry.value = m
    }
  })
}, { deep: true })

function fmtTime(iso) {
  if (!iso) return '——'
  return new Date(iso).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
}

const todayStr = new Date().toLocaleDateString('th-TH', {
  year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
})

// ── Clear Today ──────────────────────────────────────────────────────
const showConfirm = ref(false)
const clearing    = ref(false)
function confirmClearToday() { showConfirm.value = true }
async function doClearToday() {
  showConfirm.value = false; clearing.value = true
  try { await fetch(CLEAR_TODAY_URL, { method: 'DELETE' }); await refresh() }
  catch { /* ignore */ } finally { clearing.value = false }
}

// ── Last fetch label ─────────────────────────────────────────────────
const now = ref(new Date())
setInterval(() => { now.value = new Date() }, 5000)
const lastFetchStr = computed(() => {
  if (!lastFetch.value) return 'รอข้อมูล...'
  const diff = Math.floor((now.value - lastFetch.value) / 1000)
  return diff < 60 ? `${diff} วินาทีที่แล้ว` : `${Math.floor(diff / 60)} นาทีที่แล้ว`
})
</script>
