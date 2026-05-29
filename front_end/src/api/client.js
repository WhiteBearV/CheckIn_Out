// client.js — fetch wrapper ที่แนบ JWT token ทุก request
// เก็บ token ใน localStorage; 401 → ล้าง token + redirect ไป /login

const TOKEN_KEY = 'fr_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else       localStorage.removeItem(TOKEN_KEY)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

/**
 * authFetch — เหมือน fetch ปกติ แต่แนบ Authorization: Bearer <token>
 * - ถ้าได้ 401 → เคลียร์ token + redirect ไป /login
 * - body แบบ object → JSON.stringify ให้อัตโนมัติ
 */
export async function authFetch(url, opts = {}) {
  const token   = getToken()
  const headers = { ...(opts.headers || {}) }
  if (token) headers['Authorization'] = `Bearer ${token}`

  let body = opts.body
  if (body && typeof body === 'object' && !(body instanceof FormData) && !(body instanceof Blob)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json'
    body = JSON.stringify(body)
  }

  const res = await fetch(url, { ...opts, headers, body })
  if (res.status === 401) {
    clearToken()
    if (!location.pathname.startsWith('/login')) {
      location.href = '/login'
    }
  }
  return res
}

export async function login(username, password) {
  const r = await fetch('/auth/login', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ username, password }),
  })
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data.detail || `HTTP ${r.status}`)
  }
  const data = await r.json()
  setToken(data.token)
  return data  // { token, username, role }
}

export async function me() {
  const r = await authFetch('/auth/me')
  if (!r.ok) return null
  return r.json()  // { username, role }
}

export function logout() {
  clearToken()
  location.href = '/login'
}

// ─── User management ──────────────────────────────────────────────────────────
export async function listUsers() {
  const r = await authFetch('/users')
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`)
  return r.json()
}

export async function addUser(username, password, role) {
  const r = await authFetch('/users', { method: 'POST', body: { username, password, role } })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`)
  return r.json()
}

export async function deleteUser(username) {
  const r = await authFetch(`/users/${encodeURIComponent(username)}`, { method: 'DELETE' })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`)
  return r.json()
}

export async function updateUserRole(username, role) {
  const r = await authFetch(`/users/${encodeURIComponent(username)}/role`, {
    method: 'PATCH', body: { role },
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`)
  return r.json()
}

export async function resetUserPassword(username, newPassword) {
  const r = await authFetch(`/users/${encodeURIComponent(username)}/reset-password`, {
    method: 'POST', body: { new_password: newPassword },
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`)
  return r.json()
}
