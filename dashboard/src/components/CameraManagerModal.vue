<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm"
      @click.self="$emit('close')"
    >
      <div class="bg-gui-panel border border-gui-border rounded-2xl shadow-2xl w-full max-w-lg mx-4 flex flex-col max-h-[90vh]">

        <!-- Header -->
        <div class="px-5 py-4 border-b border-gui-border flex items-center justify-between shrink-0">
          <h3 class="font-bold text-base text-gui-text">จัดการกล้อง</h3>
          <button @click="$emit('close')"
            class="text-gui-dim hover:text-gui-text transition-colors text-lg leading-none">✕</button>
        </div>

        <!-- Scrollable body -->
        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-5">

          <!-- ── รายการกล้องปัจจุบัน ── -->
          <div>
            <h4 class="text-xs font-semibold text-gui-dim uppercase tracking-wider mb-2">กล้องที่มีอยู่</h4>
            <div v-if="cameras.length === 0" class="text-sm text-gui-dim/60 py-2">ยังไม่มีกล้อง</div>
            <div v-else class="space-y-2">
              <div
                v-for="cam in cameras"
                :key="cam.id"
                class="flex items-center gap-3 bg-gui-bg/60 border border-gui-border/60 rounded-xl px-3 py-2.5"
              >
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-medium text-gui-text truncate">{{ cam.name }}</div>
                  <div class="text-[11px] text-gui-dim/70 flex items-center gap-2 mt-0.5 flex-wrap">
                    <span class="px-1.5 py-0.5 rounded bg-gui-border/40 font-mono">{{ cam.id }}</span>
                    <span>{{ cam.source_type === 'rtsp' ? 'IP Camera' : 'Webcam' }}</span>
                  </div>
                </div>

                <!-- Flip toggle -->
                <div class="flex flex-col items-center gap-0.5 shrink-0">
                  <button
                    @click="toggleFlip(cam)"
                    :disabled="flippingId === cam.id"
                    :class="cam.flip
                      ? 'bg-gui-in border-gui-in/60'
                      : 'bg-gui-border/30 border-gui-border'"
                    class="relative inline-flex items-center w-9 h-5 rounded-full border transition-colors p-0.5 disabled:opacity-40"
                    :title="cam.flip ? 'Flip เปิด — คลิกเพื่อปิด' : 'Flip ปิด — คลิกเพื่อเปิด'"
                  >
                    <span
                      :class="cam.flip ? 'translate-x-4' : 'translate-x-0'"
                      class="w-3 h-3 rounded-full bg-white shadow transition-transform shrink-0"
                    />
                  </button>
                  <span class="text-[9px]" :class="cam.flip ? 'text-gui-in' : 'text-gui-dim/40'">Flip</span>
                </div>

                <button
                  @click="confirmDelete(cam)"
                  :disabled="deletingId === cam.id"
                  class="shrink-0 px-2.5 py-1 rounded-lg text-xs border border-gui-fail/30 text-gui-fail/70
                         hover:border-gui-fail/60 hover:text-gui-fail transition-colors
                         disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {{ deletingId === cam.id ? '...' : '🗑' }}
                </button>
              </div>
            </div>
          </div>

          <!-- ── Divider ── -->
          <div class="border-t border-gui-border/40" />

          <!-- ── ฟอร์มเพิ่มกล้องใหม่ ── -->
          <div>
            <h4 class="text-xs font-semibold text-gui-dim uppercase tracking-wider mb-3">เพิ่มกล้องใหม่</h4>

            <!-- ชื่อกล้อง -->
            <div class="mb-3">
              <label class="block text-xs text-gui-dim mb-1">ชื่อกล้อง <span class="text-gui-fail">*</span></label>
              <input
                v-model="form.name"
                type="text"
                placeholder="เช่น กล้องหน้าประตู"
                :class="nameDupError ? 'border-gui-fail/60 focus:border-gui-fail' : 'border-gui-border focus:border-gui-in/60'"
                class="w-full bg-gui-bg border rounded-lg px-3 py-2 text-sm text-gui-text
                       placeholder:text-gui-dim/40 focus:outline-none transition-colors"
              />
              <p v-if="nameDupError" class="text-[11px] text-gui-fail mt-1">{{ nameDupError }}</p>
            </div>

            <!-- ประเภทกล้อง -->
            <div class="mb-3">
              <label class="block text-xs text-gui-dim mb-1">ประเภทกล้อง</label>
              <div class="flex gap-2">
                <button
                  @click="form.source_type = 'rtsp'"
                  :class="form.source_type === 'rtsp'
                    ? 'bg-gui-in/20 text-gui-in border-gui-in/50'
                    : 'bg-gui-bg text-gui-dim border-gui-border hover:border-gui-in/30'"
                  class="flex-1 py-2 rounded-lg text-xs font-medium border transition-colors"
                >IP Camera (URL)</button>
                <button
                  @click="form.source_type = 'usb'"
                  :class="form.source_type === 'usb'
                    ? 'bg-gui-in/20 text-gui-in border-gui-in/50'
                    : 'bg-gui-bg text-gui-dim border-gui-border hover:border-gui-in/30'"
                  class="flex-1 py-2 rounded-lg text-xs font-medium border transition-colors"
                >Webcam (Port)</button>
              </div>
            </div>

            <!-- URL / Port -->
            <div class="mb-3">
              <label class="block text-xs text-gui-dim mb-1">
                {{ form.source_type === 'rtsp' ? 'URL กล้อง (RTSP / HTTP)' : 'หมายเลข Port / Index' }}
                <span class="text-gui-fail">*</span>
              </label>
              <input
                v-if="form.source_type === 'rtsp'"
                v-model="form.source"
                type="text"
                placeholder="rtsp://admin:pass@192.168.1.x:554/..."
                :class="sourceDupError ? 'border-gui-fail/60 focus:border-gui-fail' : 'border-gui-border focus:border-gui-in/60'"
                class="w-full bg-gui-bg border rounded-lg px-3 py-2 text-sm text-gui-text
                       placeholder:text-gui-dim/40 focus:outline-none font-mono transition-colors"
              />
              <input
                v-else
                v-model="form.source"
                type="number"
                min="0"
                max="99"
                placeholder="0"
                :class="sourceDupError ? 'border-gui-fail/60 focus:border-gui-fail' : 'border-gui-border focus:border-gui-in/60'"
                class="w-full bg-gui-bg border rounded-lg px-3 py-2 text-sm text-gui-text
                       placeholder:text-gui-dim/40 focus:outline-none font-mono transition-colors"
              />
              <p v-if="sourceDupError" class="text-[11px] text-gui-fail mt-1">{{ sourceDupError }}</p>
              <p v-else class="text-[11px] text-gui-dim/50 mt-1">
                <template v-if="form.source_type === 'usb'">
                  Webcam ในตัว = 0, กล้องต่อพ่วง = 1, 2, ...
                </template>
                <template v-else>
                  ตัวอย่าง: rtsp://admin:pass@192.168.1.13:554/unicast/c1/s0/live
                </template>
              </p>
            </div>

            <!-- Flip toggle -->
            <div class="flex items-center justify-between py-2.5 px-3 rounded-lg bg-gui-bg/60 border border-gui-border/60">
              <div>
                <div class="text-sm font-medium text-gui-text">Flip ภาพ (กระจก)</div>
                <div class="text-[11px] text-gui-dim/60 mt-0.5">สลับซ้าย-ขวาของภาพกล้อง</div>
              </div>
              <button
                @click="form.flip = !form.flip"
                :class="form.flip
                  ? 'bg-gui-in border-gui-in/60'
                  : 'bg-gui-border/30 border-gui-border'"
                class="relative inline-flex items-center w-11 h-6 rounded-full border transition-colors shrink-0 p-0.5"
              >
                <span
                  :class="form.flip ? 'translate-x-5' : 'translate-x-0'"
                  class="w-4 h-4 rounded-full bg-white shadow transition-transform shrink-0"
                />
              </button>
            </div>

            <!-- Error -->
            <p v-if="addError" class="text-xs text-gui-fail mt-2">{{ addError }}</p>
          </div>

        </div>

        <!-- Footer -->
        <div class="px-5 py-4 border-t border-gui-border flex items-center justify-end gap-3 shrink-0">
          <button @click="$emit('close')"
            class="px-4 py-1.5 rounded-lg text-sm border border-gui-border text-gui-dim hover:text-gui-text transition-colors">
            ปิด
          </button>
          <button
            @click="submitAdd"
            :disabled="adding || !form.name.trim() || !form.source.toString().trim() || !!nameDupError || !!sourceDupError"
            class="px-5 py-1.5 rounded-lg text-sm font-semibold
                   bg-gui-in/20 text-gui-in border border-gui-in/40
                   hover:bg-gui-in/30 transition-colors
                   disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {{ adding ? 'กำลังเพิ่ม...' : '+ เพิ่มกล้อง' }}
          </button>
        </div>

      </div>
    </div>

    <!-- Delete confirm dialog -->
    <div v-if="deleteTarget"
      class="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm"
      @click.self="deleteTarget = null"
    >
      <div class="bg-gui-panel border border-gui-fail/40 rounded-2xl shadow-2xl p-6 w-full max-w-sm mx-4">
        <h3 class="font-bold text-base mb-1 text-gui-text">ยืนยันการลบกล้อง</h3>
        <p class="text-sm text-gui-dim mb-4">
          ลบ <span class="text-gui-fail font-semibold">{{ deleteTarget.name }}</span>
          ({{ deleteTarget.id }}) ออกจากระบบ?
          <br/>
          <span class="text-[11px] text-gui-dim/60">กระบวนการที่กำลังรันจะถูกหยุดโดยอัตโนมัติ</span>
        </p>
        <div class="flex gap-3 justify-end">
          <button @click="deleteTarget = null"
            class="px-4 py-1.5 rounded-lg text-sm border border-gui-border text-gui-dim hover:text-gui-text transition-colors">
            ยกเลิก
          </button>
          <button @click="doDelete"
            class="px-4 py-1.5 rounded-lg text-sm font-semibold bg-gui-fail/15 text-gui-fail border border-gui-fail/40 hover:bg-gui-fail/25 transition-colors">
            ยืนยัน ลบกล้อง
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'

const props = defineProps({
  cameras: { type: Array, default: () => [] },
  apiBase: { type: String, default: '/api' },
})

const emit = defineEmits(['close', 'changed'])

// ── Add form ──────────────────────────────────────────────────────────
const form = reactive({
  name:        '',
  source_type: 'usb',
  source:      '0',
  flip:        false,
})
const adding   = ref(false)
const addError = ref('')

// ── Duplicate validation (real-time) ─────────────────────────────────
const nameDupError = computed(() => {
  const trimmed = form.name.trim().toLowerCase()
  if (!trimmed) return ''
  return props.cameras.some(c => c.name.trim().toLowerCase() === trimmed)
    ? `ชื่อ "${form.name.trim()}" ถูกใช้ไปแล้ว`
    : ''
})

const sourceDupError = computed(() => {
  const trimmed = form.source.toString().trim().toLowerCase()
  if (!trimmed) return ''
  return props.cameras.some(c => c.source?.toString().trim().toLowerCase() === trimmed)
    ? `${form.source_type === 'rtsp' ? 'URL' : 'Port'} นี้ถูกใช้ไปแล้ว`
    : ''
})

async function submitAdd() {
  addError.value = ''
  const name   = form.name.trim()
  const source = form.source.toString().trim()
  if (!name || !source || nameDupError.value || sourceDupError.value) return

  adding.value = true
  try {
    const res = await fetch(`${props.apiBase}/cameras`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        source_type: form.source_type,
        source,
        flip: form.flip,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      addError.value = err.detail ?? `Error ${res.status}`
      return
    }
    // reset form
    form.name        = ''
    form.source_type = 'usb'
    form.source      = '0'
    form.flip        = false
    emit('changed')
  } catch (e) {
    addError.value = e.message ?? 'เชื่อมต่อ API ไม่ได้'
  } finally {
    adding.value = false
  }
}

// ── Toggle Flip ───────────────────────────────────────────────────────
const flippingId = ref(null)

async function toggleFlip(cam) {
  flippingId.value = cam.id
  try {
    const res = await fetch(`${props.apiBase}/cameras/${cam.id}/flip`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ flip: !cam.flip }),
    })
    if (res.ok) {
      emit('changed')
    }
  } catch { /* ignore */ } finally {
    flippingId.value = null
  }
}

// ── Delete ────────────────────────────────────────────────────────────
const deleteTarget = ref(null)
const deletingId   = ref(null)

function confirmDelete(cam) {
  deleteTarget.value = cam
}

async function doDelete() {
  if (!deleteTarget.value) return
  const cam = deleteTarget.value
  deleteTarget.value = null
  deletingId.value = cam.id
  try {
    const res = await fetch(`${props.apiBase}/cameras/${cam.id}`, { method: 'DELETE' })
    if (res.ok) {
      emit('changed')
    }
  } catch { /* ignore */ } finally {
    deletingId.value = null
  }
}
</script>
