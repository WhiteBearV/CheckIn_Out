// composables/useAuth.js — Auth state + JWT token management
import { ref, computed } from 'vue'

const TOKEN_KEY = 'face_auth_token'
const USER_KEY  = 'face_auth_user'

const token = ref(localStorage.getItem(TOKEN_KEY) || '')
const user  = ref(JSON.parse(localStorage.getItem(USER_KEY) || 'null'))

// ── Computed ──────────────────────────────────────────────────────────────────

export const isAuthenticated = computed(() => !!token.value)

export const currentUser = computed(() => user.value)

export const isAdmin = computed(() =>
  user.value?.permissions?.includes('*') || false
)

// ── Permission check ──────────────────────────────────────────────────────────

export function hasPermission(permission) {
  const perms = user.value?.permissions || []
  return perms.includes('*') || perms.includes(permission)
}

// ── Auth token for API calls ──────────────────────────────────────────────────

export function getToken() {
  return token.value
}

// ── Login ─────────────────────────────────────────────────────────────────────

export async function login(username, password) {
  const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
  const res = await fetch(`${BASE}/auth/login`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'เข้าสู่ระบบไม่สำเร็จ')
  }
  const data = await res.json()
  token.value = data.token
  user.value  = {
    username:     data.username,
    display_name: data.display_name,
    role:         data.role,
    permissions:  data.permissions,
  }
  localStorage.setItem(TOKEN_KEY, data.token)
  localStorage.setItem(USER_KEY,  JSON.stringify(user.value))
  return data
}

// ── Logout ────────────────────────────────────────────────────────────────────

export function logout() {
  token.value = ''
  user.value  = null
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// ── Verify token on app load (check expiry) ───────────────────────────────────

export function checkTokenExpiry() {
  if (!token.value) return false
  try {
    const [, payload] = token.value.split('.')
    const data = JSON.parse(atob(payload))
    if (data.exp && data.exp * 1000 < Date.now()) {
      logout()
      return false
    }
    return true
  } catch {
    logout()
    return false
  }
}
