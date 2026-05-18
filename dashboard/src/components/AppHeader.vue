<template>
  <header class="bg-gui-panel border-b border-gui-border px-5 py-3
                 flex items-center justify-between gap-4 shrink-0">

    <!-- ── ซ้าย: Logo + Title ── -->
    <div class="flex items-center gap-3">
      <div class="w-9 h-9 rounded-xl bg-gui-in/15 flex items-center
                  justify-center text-xl shrink-0">
        👁
      </div>
      <div class="leading-tight">
        <h1 class="text-sm font-semibold text-gui-text">Face Attendance</h1>
        <p class="text-xs text-gui-dim">Dashboard</p>
      </div>
    </div>

    <!-- ── ขวา: Theme + วันที่ + เวลา + User ── -->
    <div class="flex items-center gap-3 md:gap-5 text-sm">

      <!-- Theme picker -->
      <div class="flex items-center gap-1 bg-gui-bg rounded-lg p-0.5 border border-gui-border/60">
        <button
          v-for="opt in themeOptions"
          :key="opt.value"
          @click="setTheme(opt.value)"
          :title="opt.label"
          :class="theme === opt.value
            ? 'bg-gui-panel text-gui-text shadow-sm'
            : 'text-gui-dim hover:text-gui-text'"
          class="px-2 py-1 rounded-md text-xs transition-colors"
        >
          {{ opt.icon }}
        </button>
      </div>

      <!-- วันที่ (ซ่อนบนจอเล็ก) -->
      <div class="hidden sm:block text-right">
        <div class="text-xs text-gui-dim">วันที่</div>
        <div class="text-xs font-medium leading-tight">{{ dateStr }}</div>
      </div>

      <!-- เวลา real-time -->
      <div class="text-right">
        <div class="text-xs text-gui-dim">เวลา</div>
        <div class="font-mono text-base font-bold text-gui-in tabular-nums">
          {{ timeStr }}
        </div>
      </div>

      <!-- User info + logout -->
      <div v-if="currentUser" class="relative" ref="userMenuRef">
        <button
          @click="showMenu = !showMenu"
          class="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-gui-border
                 text-gui-dim hover:text-gui-text hover:border-gui-in/40 transition-colors"
        >
          <span class="text-sm">👤</span>
          <span class="text-xs font-medium hidden sm:block max-w-24 truncate">
            {{ currentUser.display_name }}
          </span>
          <span class="text-xs text-gui-dim">▾</span>
        </button>

        <!-- Dropdown -->
        <div v-if="showMenu"
             class="absolute right-0 top-full mt-1 z-50 w-56
                    bg-gui-panel border border-gui-border rounded-xl shadow-xl overflow-hidden">
          <div class="px-4 py-3 border-b border-gui-border">
            <div class="text-sm font-semibold text-gui-text">{{ currentUser.display_name }}</div>
            <div class="text-xs text-gui-dim">@{{ currentUser.username }}</div>
            <div class="mt-1">
              <span class="text-xs px-2 py-0.5 rounded-full border
                           bg-gui-in/10 text-gui-in border-gui-in/20">
                {{ currentUser.role }}
              </span>
            </div>
          </div>
          <button
            @click="doLogout"
            class="w-full text-left px-4 py-3 text-sm text-gui-fail
                   hover:bg-gui-fail/10 transition-colors"
          >
            ออกจากระบบ
          </button>
        </div>
      </div>

    </div>
  </header>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from '@/composables/useTheme.js'
import { currentUser, logout } from '@/composables/useAuth.js'

const { theme, setTheme } = useTheme()
const router = useRouter()

const themeOptions = [
  { value: 'light', icon: '☀', label: 'ธีมสว่าง'    },
  { value: 'dark',  icon: '🌙', label: 'ธีมมืด'      },
  { value: 'auto',  icon: '💻', label: 'ตามระบบ (Auto)' },
]

// ── นาฬิกา real-time ──────────────────────────────────────────────────────────
const now = ref(new Date())
let clockTimer = null
onMounted(() => {
  clockTimer = setInterval(() => { now.value = new Date() }, 1000)
})
onUnmounted(() => clearInterval(clockTimer))

const dateStr = computed(() =>
  now.value.toLocaleDateString('th-TH', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'short',
  })
)
const timeStr = computed(() =>
  now.value.toLocaleTimeString('th-TH', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
)

// ── User menu ─────────────────────────────────────────────────────────────────
const showMenu   = ref(false)
const userMenuRef = ref(null)

function doLogout() {
  showMenu.value = false
  logout()
  router.push('/login')
}

// ปิด menu เมื่อคลิกข้างนอก
function onClickOutside(e) {
  if (userMenuRef.value && !userMenuRef.value.contains(e.target)) {
    showMenu.value = false
  }
}
onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>
