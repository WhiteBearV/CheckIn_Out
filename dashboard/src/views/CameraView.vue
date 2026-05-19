<template>
  <!-- Fullscreen mode ใช้ position:fixed ครอบ viewport ทั้งหมด
       เพื่อหลีกเลี่ยงปัญหา flex chain height calculation ใน Firefox -->
  <div :class="isFullscreen
    ? 'fixed inset-0 z-[200] flex flex-col bg-[#0a0a0a] overflow-hidden'
    : 'p-4 md:p-6 max-w-screen-2xl mx-auto w-full space-y-4'">

    <!-- ════ FULLSCREEN WRAPPER ════════════════════════════════════════ -->
    <div
      :class="isFullscreen
        ? 'flex flex-row flex-1 min-h-0 overflow-hidden'
        : 'grid grid-cols-1 lg:grid-cols-3 gap-4'"
      :style="isFullscreen ? undefined : 'min-height: 520px'"
    >

      <!-- ── กล้อง (ซ้าย): ทุกกล้องใน box เดียว ─────────────────────── -->
      <div
        class="bg-black flex flex-col overflow-hidden"
        :class="isFullscreen
          ? 'flex-1 min-w-0 min-h-0 border-r border-gui-border'
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
          <div class="flex items-center gap-2">
            <!-- System Mode Badge -->
            <span
              v-if="systemMode === 'cctv'"
              class="text-xs px-2 py-0.5 rounded-full font-semibold
                     bg-blue-500/15 text-blue-400 border border-blue-500/30"
              title="อยู่นอกช่วงเวลาทำงาน — โหมด CCTV"
            >🖥 CCTV Mode</span>
            <span
              v-else-if="systemMode === 'face'"
              class="text-xs px-2 py-0.5 rounded-full font-medium
                     bg-gui-in/10 text-gui-in/70"
              title="อยู่ในช่วงเวลาทำงาน — Face Recognition เปิดอยู่"
            >🕐 {{ activeWindowStr }}</span>
            <!-- Camera status -->
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
        </div>

        <!-- ══════════════════════════════════════════════════════════════
             Feed Area — CSS absolute layout (img ทุกตัวอยู่ใน DOM เสมอ)
             ไม่ใช้ v-if/v-else เพื่อป้องกัน MJPEG ขาด connection
             ════════════════════════════════════════════════════════════ -->
        <div class="flex-1 min-h-0 relative overflow-hidden" :style="isFullscreen ? undefined : `min-height: ${feedMinHeight}px`">
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

              <!-- ─ เส้นคั่น grid (normal mode) ─ -->
              <div v-if="!focusedCamId && gridLayout[cam.id]?.onPage && gridLayout[cam.id]?.col > 0"
                   class="absolute left-0 inset-y-0 w-px bg-gui-border/50 z-30 pointer-events-none" />
              <div v-if="!focusedCamId && gridLayout[cam.id]?.onPage && gridLayout[cam.id]?.row > 0"
                   class="absolute top-0 inset-x-0 h-px bg-gui-border/50 z-30 pointer-events-none" />

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

              <!-- ─ LIVE stream ─ -->
              <img
                :key="`stream-${cam.id}-${getCamState(cam.id).streamStartTs}`"
                v-if="isLive(cam.id) && hasRecentFrame(cam.id) && !getCamState(cam.id).streamError"
                :src="streamUrlFor(cam.id)"
                alt="Face Recognition Stream"
                class="absolute inset-0 w-full h-full object-contain z-[1]"
                @error="() => onStreamError(cam.id)"
              />

              <!-- ─ OFFLINE / STARTING / STREAM ERROR ─
                   v-else ต้องอยู่ติดกับ v-if ของ img โดยไม่มี element คั่น ─ -->
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

                <!-- Thumbnail: ข้อความเล็ก -->
                <div v-if="isThumbnail(cam.id)" class="relative z-20 text-[9px] text-gui-dim/70">
                  {{ getCamState(cam.id).streamError ? 'สตรีมขาด' : isLive(cam.id) || getCamState(cam.id).isBooting ? 'กำลังดาวน์โหลด...' : 'ออฟไลน์' }}
                </div>

                <!-- Normal/focused: ปุ่มเปิด, Retry หรือ Downloading -->
                <template v-else>
                  <!-- Stream error: ปุ่ม retry -->
                  <div v-if="getCamState(cam.id).streamError"
                       class="relative z-20 flex flex-col items-center gap-3">
                    <span class="text-white/40 text-[10px]">สตรีมขาดการเชื่อมต่อ</span>
                    <button @click.stop="retryStream(cam.id)"
                      class="btn-cam-start px-5 py-2 rounded-lg text-xs transition-colors"
                    >↻ รีเฟรชสตรีม</button>
                  </div>

                  <!-- ปุ่มเปิด: เฉพาะเมื่อกล้องดับสนิท ไม่รัน ไม่โหลด และมีสิทธิ์ -->
                  <div v-else-if="!isLive(cam.id) && !getCamState(cam.id).isStarting && !getCamState(cam.id).isBooting && hasPermission('cameras.manage')"
                       class="relative z-20 flex flex-col items-center gap-2">
                    <button @click.stop="startFace(cam.id)"
                      class="btn-cam-start px-5 py-2 rounded-lg text-xs transition-colors"
                    >▶ เปิด</button>
                  </div>

                  <!-- Downloading screen: แสดงตลอดจนกว่ากล้องจะมี frame จริง -->
                  <div v-else class="relative z-20 flex flex-col items-center gap-3 w-full px-6">
                    <span class="text-white/50 text-[9px] tracking-widest uppercase">Face Attendance System</span>
                    <span class="text-blue-300/90 text-[11px] font-medium">กำลังดาวน์โหลด...</span>
                    <div class="w-full max-w-[180px] h-[4px] bg-white/10 rounded-full overflow-hidden">
                      <div class="h-full bg-green-400/80 rounded-full"
                           :style="`width:${bootProgressFor(cam.id)}%;transition:width 0.8s ease`"/>
                    </div>
                    <span v-if="getCamState(cam.id).bootMsg"
                          class="text-white/35 text-[9px] text-center leading-tight">
                      {{ getCamState(cam.id).bootMsg }}
                    </span>
                    <div class="flex items-center gap-1.5 mt-0.5">
                      <div v-for="i in 5" :key="i" class="w-1.5 h-1.5 rounded-full dl-dot-cam"
                           :style="`animation-delay:${(i-1)*0.18}s`"/>
                    </div>
                  </div>
                </template>

              </div>

              <!-- ─ Hover highlight (อยู่หลัง v-if/v-else block เสมอ) ─ -->
              <div class="absolute inset-0 bg-gui-in/0 group-hover:bg-gui-in/8 transition-colors pointer-events-none z-[2]" />
              <div v-if="isThumbnail(cam.id)"
                   class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20">
                <span class="bg-black/70 text-white text-[9px] px-2 py-0.5 rounded-full">ขยาย ⛶</span>
              </div>

            </div>

          </div>
        </div>
        <!-- /Feed Area -->

        <!-- Controls: per-camera toggles + fullscreen -->
        <div class="border-t border-gui-border shrink-0 bg-gui-panel/80">

          <!-- แถวหลัก -->
          <div class="px-4 py-3 flex items-center gap-3 flex-wrap">

          <!-- Start/Stop all -->
          <button
            v-if="cameras.length > 1 && hasPermission('cameras.manage')"
            @click="anyLive ? stopAll() : startAll()"
            :disabled="anyStarting"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                   transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            :class="anyLive ? 'btn-cam-stop' : 'btn-cam-start'"
          >
            {{ anyLive ? '⏹ หยุดทั้งหมด' : '▶ เปิดทั้งหมด' }}
          </button>

          <!-- Single-cam toggle for 1 camera -->
          <button
            v-if="cameras.length === 1 && hasPermission('cameras.manage')"
            @click="toggleFace(cameras[0].id)"
            :disabled="getCamState(cameras[0].id).isStarting"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                   transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            :class="isLive(cameras[0].id) ? 'btn-cam-stop' : 'btn-cam-start'"
          >
            <span>{{ isLive(cameras[0].id) ? '⏹' : '▶' }}</span>
            {{ cameras[0].name }}
          </button>

          <!-- ปุ่มเปิด/ปิดแสดงปุ่มทีละตัว -->
          <button
            v-if="cameras.length > 1 && hasPermission('cameras.manage')"
            @click="showPerCamControls = !showPerCamControls"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                   border border-gui-border text-gui-dim hover:text-gui-text
                   hover:border-gui-in/40 transition-colors"
            :title="showPerCamControls ? 'ซ่อนปุ่มรายกล้อง' : 'แสดงปุ่มรายกล้อง'"
          >
            ☰ รายกล้อง
            <span class="text-[10px] opacity-60">{{ showPerCamControls ? '▲' : '▼' }}</span>
          </button>

          <!-- Pagination -->
          <template v-if="totalPages > 1">
            <div class="ml-auto flex items-center gap-1">
              <button @click="prevPage" :disabled="currentPage === 0"
                class="px-2.5 py-1.5 rounded-lg text-xs border border-gui-border text-gui-dim
                       hover:text-gui-text hover:border-gui-in/40 transition-colors
                       disabled:opacity-30 disabled:cursor-not-allowed"
                title="หน้าก่อนหน้า">‹</button>
              <span class="text-xs text-gui-dim px-1.5 tabular-nums font-mono">
                {{ currentPage + 1 }}&thinsp;/&thinsp;{{ totalPages }}
              </span>
              <button @click="nextPage" :disabled="currentPage >= totalPages - 1"
                class="px-2.5 py-1.5 rounded-lg text-xs border border-gui-border text-gui-dim
                       hover:text-gui-text hover:border-gui-in/40 transition-colors
                       disabled:opacity-30 disabled:cursor-not-allowed"
                title="หน้าถัดไป">›</button>
            </div>
          </template>

          <button
            v-if="hasPermission('cameras.manage')"
            @click="showCameraManager = true"
            :class="totalPages <= 1 ? 'ml-auto' : ''"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
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

          </div><!-- /แถวหลัก -->

          <!-- แถวปุ่มรายกล้อง (ซ่อน/แสดงได้) -->
          <div
            v-show="showPerCamControls && cameras.length > 1 && hasPermission('cameras.manage')"
            class="px-4 pb-3 flex flex-wrap gap-2 border-t border-gui-border/40 pt-2.5"
          >
            <template v-for="cam in cameras" :key="`ctrl-${cam.id}`">
              <button
                @click="toggleFace(cam.id)"
                :disabled="getCamState(cam.id).isStarting"
                class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                       transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                :class="isLive(cam.id) ? 'btn-cam-stop' : 'btn-cam-start'"
              >
                <span>{{ isLive(cam.id) ? '⏹' : '▶' }}</span>
                <span>{{ cam.name }}</span>
                <span v-if="isLive(cam.id) && frameAgeFor(cam.id) !== null"
                  class="text-[10px] opacity-70">{{ frameAgeFor(cam.id) }}s</span>
              </button>
            </template>
          </div>

        </div><!-- /Controls -->

      </div>
      <!-- ── /กล้อง ─────────────────────────────────────────────── -->

      <!-- ── Right panel ────────────────────────────────────────────
           Normal mode : LiveDetection + สถานะระบบ + วิธีใช้
           Fullscreen  : รายชื่อที่พบวันนี้ (kiosk sidebar)
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
            <div class="space-y-3 text-sm overflow-y-auto" style="max-height: 220px">
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

          <div v-if="hasPermission('cameras.manage')"
               class="bg-gui-panel border border-gui-border rounded-xl p-4 shrink-0">
            <h3 class="font-semibold text-sm mb-3 text-gui-dim">วิธีใช้</h3>
            <ul class="text-xs text-gui-dim space-y-1.5 leading-relaxed">
              <li>• กด <span class="text-gui-in font-medium">▶ ชื่อกล้อง</span> เพื่อ start กล้องนั้น</li>
              <li>• กด <span class="text-gui-in font-medium">▶ เปิดทั้งหมด</span> เพื่อ start พร้อมกัน</li>
              <li>• แต่ละกล้องรัน main.py แยกกัน พร้อมกันได้</li>
              <li>• Panel ขวาแสดงสถานะ liveness แบบ real-time</li>
            </ul>
          </div>

        </template>

        <!-- ─ Fullscreen mode: รายชื่อที่พบวันนี้ (kiosk sidebar) ──────── -->
        <template v-else>

          <div class="px-4 py-3 border-b border-gui-border bg-gui-panel flex items-center justify-between shrink-0">
            <div class="flex items-center gap-2">
              <span class="text-gui-in font-bold text-base">▣</span>
              <span class="font-semibold text-sm text-gui-text">รายชื่อที่พบวันนี้</span>
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

          <div class="px-4 py-2.5 border-t border-gui-border shrink-0 bg-gui-panel/30
                      flex items-center justify-between">
            <span class="text-[11px] text-gui-dim">{{ todayStr }}</span>
            <span class="text-sm font-mono font-semibold text-gui-text tabular-nums">
              {{ clockStr }}
            </span>
          </div>

        </template>

      </div>
      <!-- ── /Right panel ────────────────────────────────────────── -->

    </div>
    <!-- ════ /FULLSCREEN WRAPPER ════════════════════════════════════ -->

    <!-- ══ แถบสถานะ refresh (ซ่อนใน fullscreen) ══════════════════ -->
    <template v-if="!isFullscreen">
    <div class="flex items-center justify-between gap-3 text-xs">
      <div class="flex items-center gap-2 text-gui-dim">
        <span class="w-2 h-2 rounded-full shrink-0"
          :class="attendError ? 'bg-gui-fail' : 'bg-gui-in animate-pulse-slow'"/>
        <span v-if="attendError" class="text-gui-fail">เชื่อมต่อ API ไม่ได้: {{ attendError }}</span>
        <span v-else>อัพเดตเมื่อ {{ lastFetchStr }}</span>
      </div>
      <div class="flex items-center gap-2">
        <button v-if="hasPermission('attendance.clear')" @click="confirmClearToday" :disabled="clearing"
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

    </template><!-- /แถบสถานะ refresh -->

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
      <div v-if="showConfirm" class="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-sm"
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

  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import LiveDetection       from '@/components/LiveDetection.vue'
import CameraManagerModal  from '@/components/CameraManagerModal.vue'
import { useAttendance }    from '@/composables/useAttendance.js'
import { useLiveSession }   from '@/composables/useLiveSession.js'
import { isUIFullscreen }   from '@/composables/useUIFullscreen.js'
import { apiFetch, apiPost, apiDelete, streamUrl } from '@/api/attendance.js'
import { hasPermission } from '@/composables/useAuth.js'

// ── Route ───────────────────────────────────────────────────────────
const route = useRoute()

// ── Config ─────────────────────────────────────────────────────────
const BASE_URL        = import.meta.env.VITE_API_BASE_URL ?? '/api'
const API_BASE        = BASE_URL
const CLEAR_TODAY_URL = `${API_BASE}/attendance/today/all`
const POLL_MS         = 2_000

// ── System Mode (Active Windows — เหมือน GUI main.py) ──────────────
// poll ทุก 30 วินาที — auto-enter CCTV เมื่อนอก active window,
//                      auto-checkout เมื่อ transition face→cctv
const systemMode      = ref(null)   // 'face' | 'cctv' | null
const activeWindowStr = ref('')
let   _prevSysMode    = null

async function fetchSystemMode() {
  try {
    const data = await apiFetch('/system/mode')
    const newMode = data.mode   // 'face' | 'cctv'

    if (data.active_windows?.length) {
      const w = data.active_windows[0]
      activeWindowStr.value = `${w.start}–${w.end}`
    }

    // face→cctv: trigger auto-checkout ฝั่ง frontend ด้วย (backend ก็ทำ แต่ frontend refresh)
    if (_prevSysMode === 'face' && newMode === 'cctv') {
      apiPost('/attendance/auto-checkout')
        .then(() => refresh()).catch(() => {})
    }

    // เข้า CCTV fullscreen อัตโนมัติเมื่อ mode=cctv
    if (newMode === 'cctv' && !isFullscreen.value) {
      isFullscreen.value = true
    }
    // ออก fullscreen เมื่อกลับมา face mode (เฉพาะที่เข้าอัตโนมัติ)
    if (_prevSysMode === 'cctv' && newMode === 'face' && isFullscreen.value) {
      isFullscreen.value = false
    }

    _prevSysMode     = newMode
    systemMode.value = newMode
  } catch { /* offline / API ยังไม่พร้อม */ }
}

// ── Camera List ─────────────────────────────────────────────────────
const cameras = ref([])

async function loadCameras() {
  try {
    cameras.value = await apiFetch('/cameras')
    cameras.value.forEach(cam => initCamState(cam))
  } catch { /* ignore */ }
}

// ── Camera Manager Modal ─────────────────────────────────────────────
const showCameraManager   = ref(false)
const showPerCamControls  = ref(false)

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
      isBooting:     false,
      bootMsg:       null,
      streamStartTs: Date.now(),
      streamError:   false,
    }
  }
}

function getCamState(camId) {
  return camStates[camId] ?? {
    faceStatus:    { running: false, pid: null, has_frame: false, frame_age_sec: null },
    isStarting:    false,
    isBooting:     false,
    bootMsg:       null,
    streamStartTs: 0,
    streamError:   false,
  }
}

// ── Focus Mode + Grid Pagination ─────────────────────────────────────
const THUMB_H          = 140
const CAMERAS_PER_PAGE = 9
const focusedCamId     = ref(null)
const currentPage      = ref(0)

// คำนวณ cols ที่เหมาะสมตามจำนวนกล้อง — ให้แถวสุดท้ายเต็มหรือน้อยกว่าครึ่ง
function getGridCols(n) {
  if (n <= 1) return 1
  if (n <= 2) return 2
  if (n <= 3) return 3
  if (n <= 4) return 2  // 2×2
  if (n <= 6) return 3  // 3×2
  if (n <= 8) return 4  // 4×2
  return 3              // 3×3
}

const totalPages = computed(() =>
  Math.max(1, Math.ceil(cameras.value.length / CAMERAS_PER_PAGE))
)

const currentPageCameras = computed(() => {
  const start = currentPage.value * CAMERAS_PER_PAGE
  return cameras.value.slice(start, start + CAMERAS_PER_PAGE)
})

// layout map: camId → { onPage, col, row, cols, rows }
const gridLayout = computed(() => {
  const cams = currentPageCameras.value
  const n    = cams.length
  const cols = getGridCols(n)
  const rows = Math.ceil(n / cols)
  const layout = {}
  cameras.value.forEach(cam => { layout[cam.id] = { onPage: false } })
  cams.forEach((cam, i) => {
    layout[cam.id] = { onPage: true, col: i % cols, row: Math.floor(i / cols), cols, rows }
  })
  return layout
})

const feedMinHeight = computed(() => {
  if (focusedCamId.value) return 320
  const n    = currentPageCameras.value.length
  const cols = getGridCols(n)
  const rows = Math.ceil(n / cols)
  return rows * 240
})

function prevPage() {
  if (currentPage.value > 0) { currentPage.value--; focusedCamId.value = null }
}
function nextPage() {
  if (currentPage.value < totalPages.value - 1) { currentPage.value++; focusedCamId.value = null }
}

watch(totalPages, (tp) => {
  if (currentPage.value >= tp) currentPage.value = Math.max(0, tp - 1)
})

function cameraStyle(camId) {
  if (cameras.value.length === 0) return ''
  const info = gridLayout.value[camId]
  const hidden = 'top:0;left:0;width:0;height:0;overflow:hidden;pointer-events:none'

  if (focusedCamId.value) {
    if (camId === focusedCamId.value) {
      const thumbN = currentPageCameras.value.filter(c => c.id !== focusedCamId.value).length
      return `top:0;left:0;right:0;bottom:${thumbN > 0 ? THUMB_H : 0}px`
    }
    if (!info?.onPage) return hidden
    const thumbCams = currentPageCameras.value.filter(c => c.id !== focusedCamId.value)
    const tIdx = thumbCams.findIndex(c => c.id === camId)
    if (tIdx === -1) return hidden
    const tN = thumbCams.length
    return `bottom:0;height:${THUMB_H}px;left:${((tIdx / tN) * 100).toFixed(3)}%;width:${(100 / tN).toFixed(3)}%`
  }

  if (!info?.onPage) return hidden
  const { col, row, cols, rows } = info
  const n          = currentPageCameras.value.length
  // กล้องในแถวสุดท้ายอาจมีน้อยกว่า cols → ยืดให้เต็มแถว
  const lastRowN   = n % cols === 0 ? cols : n % cols
  const isLastRow  = row === rows - 1
  const effCols    = isLastRow ? lastRowN : cols
  return `top:${((row / rows) * 100).toFixed(3)}%;left:${((col / effCols) * 100).toFixed(3)}%;width:${(100 / effCols).toFixed(3)}%;height:${((1 / rows) * 100).toFixed(3)}%`
}

function isThumbnail(camId) {
  return !!focusedCamId.value && camId !== focusedCamId.value && (gridLayout.value[camId]?.onPage ?? false)
}

function onCameraClick(camId) {
  if (!gridLayout.value[camId]?.onPage && !focusedCamId.value) return
  if (isThumbnail(camId)) {
    focusedCamId.value = camId
  } else if (!focusedCamId.value) {
    focusedCamId.value = camId
  }
}

// ── Boot Progress ────────────────────────────────────────────────────
const _BOOT_STEPS = {
  'กำลังโหลดฐานข้อมูลใบหน้า...':        20,
  'กำลังโหลด AI Model (InsightFace)...': 50,
  'กำลังเปิดกล้อง...':                   75,
  'กำลังติดตั้งระบบตรวจจับ...':          90,
}
function bootProgressFor(camId) {
  const state = getCamState(camId)
  if (!state.isBooting) return 100
  return _BOOT_STEPS[state.bootMsg] ?? 5
}

// ── Per-Camera Helpers ───────────────────────────────────────────────
const isLive          = (camId) => getCamState(camId).faceStatus.running ?? false
const hasRecentFrame  = (camId) => {
  const age = getCamState(camId).faceStatus.frame_age_sec
  return age !== null && age !== undefined && age <= 8
}
const frameAgeFor     = (camId) => getCamState(camId).faceStatus.frame_age_sec ?? null
const streamUrlFor    = (camId) =>
  streamUrl(`/cameras/${camId}/face-stream?t=${getCamState(camId).streamStartTs}`)
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
  if (!camStates[camId] || camStates[camId].isStarting || camStates[camId].isBooting) return
  camStates[camId].isStarting  = true
  camStates[camId].isBooting   = true
  camStates[camId].bootMsg     = null
  camStates[camId].streamError = false
  try {
    const data = await apiPost(`/cameras/${camId}/face/start`)
    if (data.ok) {
      camStates[camId].streamStartTs = Date.now()
      setTimeout(() => fetchStatus(camId), 2_000)
    } else {
      camStates[camId].isBooting = false
    }
  } catch { camStates[camId].isBooting = false } finally {
    camStates[camId].isStarting = false
  }
}

async function stopFace(camId) {
  try {
    await apiPost(`/cameras/${camId}/face/stop`)
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

function retryStream(camId) {
  if (camStates[camId]) {
    camStates[camId].streamError   = false
    camStates[camId].streamStartTs = Date.now()
  }
}

// ── Status Polling ───────────────────────────────────────────────────
async function fetchStatus(camId) {
  try {
    const data = await apiFetch(`/cameras/${camId}/face/status`)
    if (camStates[camId]) {
      camStates[camId].faceStatus = data
      camStates[camId].bootMsg    = data.boot_msg ?? null
      if (data.has_frame || !data.running) camStates[camId].isBooting = false
    }
  } catch { /* ignore */ }
}

async function fetchAllStatuses() {
  await Promise.all(cameras.value.map(cam => fetchStatus(cam.id)))
}

let pollTimer = null

// ── Fullscreen — ซ่อน Header/Nav/Footer ผ่าน App.vue (isUIFullscreen) ──────
// ไม่ใช้ fixed positioning เพื่อหลีกเลี่ยงปัญหา containing block ใน Firefox
const isFullscreen = ref(false)

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

watch(isFullscreen, (val) => {
  isUIFullscreen.value                     = val
  document.documentElement.style.overflow = val ? 'hidden' : ''
  document.body.style.overflow             = val ? 'hidden' : ''
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
let _sysModeTimer = null

onMounted(async () => {
  // โหมด CCTV (route meta.cctv = true) → เปิด fullscreen อัตโนมัติ
  if (route.meta?.cctv) isFullscreen.value = true
  await loadCameras()
  fetchAllStatuses()
  pollTimer = setInterval(fetchAllStatuses, POLL_MS)
  window.addEventListener('keydown', onKeyDown)
  // ตรวจ system mode ทันที + ทุก 30 วินาที
  await fetchSystemMode()
  _sysModeTimer = setInterval(fetchSystemMode, 30_000)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  clearInterval(_sysModeTimer)
  clearInterval(_clockTimer)
  window.removeEventListener('keydown', onKeyDown)
  // cleanup scroll lock + shared fullscreen state
  isFullscreen.value                       = false
  isUIFullscreen.value                     = false
  document.documentElement.style.overflow = ''
  document.body.style.overflow             = ''
})

// ── Attendance Data ──────────────────────────────────────────────────
const {
  persons, stats,
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
  try { await apiDelete('/attendance/today/all'); await refresh() }
  catch { /* ignore */ } finally { clearing.value = false }
}

// ── Clock + Last fetch label ─────────────────────────────────────────
const now = ref(new Date())
const _clockTimer = setInterval(() => { now.value = new Date() }, 1000)

const clockStr = computed(() =>
  now.value.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
)
const lastFetchStr = computed(() => {
  if (!lastFetch.value) return 'รอข้อมูล...'
  const diff = Math.floor((now.value - lastFetch.value) / 1000)
  return diff < 60 ? `${diff} วินาทีที่แล้ว` : `${Math.floor(diff / 60)} นาทีที่แล้ว`
})
</script>

<style scoped>
@keyframes dl-dot-cam {
  0%, 100% { opacity: 0.2; transform: scale(0.7); background: rgba(255,255,255,0.2); }
  50%       { opacity: 1;   transform: scale(1.3); background: rgba(100,210,255,0.9); }
}
.dl-dot-cam {
  background: rgba(255,255,255,0.2);
  animation: dl-dot-cam 1.2s ease-in-out infinite;
}
</style>
