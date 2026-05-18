<template>
  <div class="min-h-screen flex items-center justify-center bg-gui-bg p-4">
    <div class="w-full max-w-sm">

      <!-- Logo -->
      <div class="text-center mb-8">
        <div class="w-16 h-16 rounded-2xl bg-gui-in/15 flex items-center justify-center text-4xl mx-auto mb-3">
          👁
        </div>
        <h1 class="text-xl font-bold text-gui-text">Face Attendance</h1>
        <p class="text-sm text-gui-dim mt-1">เข้าสู่ระบบเพื่อดำเนินการต่อ</p>
      </div>

      <!-- Card -->
      <div class="bg-gui-panel border border-gui-border rounded-2xl p-6 shadow-xl">
        <form @submit.prevent="handleLogin" class="space-y-4">

          <!-- Error -->
          <div v-if="errorMsg"
               class="bg-gui-fail/10 border border-gui-fail/30 rounded-xl px-4 py-3
                      text-sm text-gui-fail text-center">
            {{ errorMsg }}
          </div>

          <!-- Username -->
          <div class="space-y-1.5">
            <label class="text-xs font-medium text-gui-dim uppercase tracking-wide">
              ชื่อผู้ใช้
            </label>
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              placeholder="username"
              required
              class="w-full bg-gui-bg border border-gui-border rounded-xl px-4 py-2.5
                     text-sm text-gui-text placeholder-gui-dim/50
                     focus:outline-none focus:border-gui-in/60 focus:ring-1 focus:ring-gui-in/30
                     transition-colors"
            />
          </div>

          <!-- Password -->
          <div class="space-y-1.5">
            <label class="text-xs font-medium text-gui-dim uppercase tracking-wide">
              รหัสผ่าน
            </label>
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              placeholder="••••••••"
              required
              class="w-full bg-gui-bg border border-gui-border rounded-xl px-4 py-2.5
                     text-sm text-gui-text placeholder-gui-dim/50
                     focus:outline-none focus:border-gui-in/60 focus:ring-1 focus:ring-gui-in/30
                     transition-colors"
            />
          </div>

          <!-- Submit -->
          <button
            type="submit"
            :disabled="loading"
            class="w-full bg-gui-in/20 hover:bg-gui-in/30 border border-gui-in/40
                   text-gui-in font-semibold rounded-xl py-2.5 text-sm
                   transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ loading ? 'กำลังเข้าสู่ระบบ...' : 'เข้าสู่ระบบ' }}
          </button>

        </form>
      </div>

      <!-- Default credentials hint -->
      <p class="text-center text-xs text-gui-dim/50 mt-4">
        Default: admin / admin1234
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { login } from '@/composables/useAuth.js'

const router   = useRouter()
const route    = useRoute()

const username = ref('')
const password = ref('')
const loading  = ref(false)
const errorMsg = ref('')

async function handleLogin() {
  errorMsg.value = ''
  loading.value  = true
  try {
    await login(username.value, password.value)
    const next = route.query.redirect || '/'
    router.replace(next)
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}
</script>
