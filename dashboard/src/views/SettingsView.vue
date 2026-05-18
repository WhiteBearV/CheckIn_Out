<template>
  <main class="p-4 md:p-6 space-y-4 max-w-screen-xl mx-auto w-full">

    <!-- Tabs -->
    <div class="flex gap-1 bg-gui-bg border border-gui-border rounded-xl p-1 w-fit">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        @click="activeTab = tab.key"
        :class="activeTab === tab.key
          ? 'bg-gui-panel text-gui-text shadow-sm'
          : 'text-gui-dim hover:text-gui-text'"
        class="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- ── Users Tab ──────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'users'" class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-base font-semibold text-gui-text">จัดการผู้ใช้</h2>
        <button @click="openAddUser"
                class="px-4 py-2 text-sm bg-gui-in/15 hover:bg-gui-in/25 border border-gui-in/30
                       text-gui-in rounded-xl transition-colors font-medium">
          + เพิ่มผู้ใช้
        </button>
      </div>

      <!-- Users table -->
      <div class="bg-gui-panel border border-gui-border rounded-2xl overflow-hidden">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gui-border text-gui-dim text-xs uppercase tracking-wide">
              <th class="text-left px-4 py-3 font-medium">ผู้ใช้</th>
              <th class="text-left px-4 py-3 font-medium">Role</th>
              <th class="text-center px-4 py-3 font-medium">สถานะ</th>
              <th class="text-left px-4 py-3 font-medium hidden md:table-cell">สร้างเมื่อ</th>
              <th class="text-right px-4 py-3 font-medium">จัดการ</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="usersLoading">
              <td colspan="5" class="text-center py-8 text-gui-dim">กำลังโหลด...</td>
            </tr>
            <tr v-else-if="users.length === 0">
              <td colspan="5" class="text-center py-8 text-gui-dim">ไม่มีผู้ใช้</td>
            </tr>
            <tr
              v-for="u in users" :key="u.id"
              class="border-b border-gui-border/50 hover:bg-gui-bg/40 transition-colors"
            >
              <td class="px-4 py-3">
                <div class="font-medium text-gui-text">{{ u.display_name }}</div>
                <div class="text-xs text-gui-dim">@{{ u.username }}</div>
              </td>
              <td class="px-4 py-3">
                <span class="px-2 py-0.5 rounded-full text-xs font-medium
                             bg-gui-in/10 text-gui-in border border-gui-in/20">
                  {{ u.role_display || u.role_name || '—' }}
                </span>
              </td>
              <td class="px-4 py-3 text-center">
                <span :class="u.is_active
                  ? 'text-gui-in bg-gui-in/10 border-gui-in/20'
                  : 'text-gui-fail bg-gui-fail/10 border-gui-fail/20'"
                  class="px-2 py-0.5 rounded-full text-xs font-medium border">
                  {{ u.is_active ? 'ใช้งาน' : 'ระงับ' }}
                </span>
              </td>
              <td class="px-4 py-3 text-gui-dim text-xs hidden md:table-cell">
                {{ u.created_at ? new Date(u.created_at).toLocaleDateString('th-TH') : '—' }}
              </td>
              <td class="px-4 py-3">
                <div class="flex gap-2 justify-end">
                  <button @click="openEditUser(u)"
                          class="px-3 py-1 text-xs border border-gui-border text-gui-dim
                                 hover:text-gui-text hover:border-gui-in/40 rounded-lg transition-colors">
                    แก้ไข
                  </button>
                  <button @click="openResetPassword(u)"
                          class="px-3 py-1 text-xs border border-gui-border text-gui-dim
                                 hover:text-gui-text hover:border-yellow-400/40 rounded-lg transition-colors">
                    รีเซ็ต PW
                  </button>
                  <button @click="confirmDeleteUser(u)"
                          class="px-3 py-1 text-xs border border-gui-fail/30 text-gui-fail/70
                                 hover:border-gui-fail/60 hover:text-gui-fail rounded-lg transition-colors">
                    ลบ
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── Roles Tab ──────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'roles'" class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-base font-semibold text-gui-text">จัดการ Roles</h2>
        <button @click="openAddRole"
                class="px-4 py-2 text-sm bg-gui-in/15 hover:bg-gui-in/25 border border-gui-in/30
                       text-gui-in rounded-xl transition-colors font-medium">
          + เพิ่ม Role
        </button>
      </div>

      <div v-if="rolesLoading" class="text-center py-8 text-gui-dim">กำลังโหลด...</div>

      <div v-for="role in roles" :key="role.id"
           class="bg-gui-panel border border-gui-border rounded-2xl p-5 space-y-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="flex items-center gap-2">
              <h3 class="font-semibold text-gui-text">{{ role.display_name }}</h3>
              <span class="text-xs text-gui-dim bg-gui-bg px-2 py-0.5 rounded-full border border-gui-border">
                {{ role.name }}
              </span>
              <span class="text-xs text-gui-dim">
                ({{ role.user_count }} ผู้ใช้)
              </span>
            </div>
            <div v-if="role.permissions?.includes('*')"
                 class="mt-1 text-xs text-gui-in font-medium">
              ทุกสิทธิ์ (Super Admin)
            </div>
          </div>
          <div class="flex gap-2">
            <button @click="openEditRole(role)"
                    class="px-3 py-1 text-xs border border-gui-border text-gui-dim
                           hover:text-gui-text hover:border-gui-in/40 rounded-lg transition-colors">
              แก้ไข
            </button>
            <button @click="confirmDeleteRole(role)"
                    :disabled="role.user_count > 0"
                    class="px-3 py-1 text-xs border border-gui-fail/30 text-gui-fail/70
                           hover:border-gui-fail/60 hover:text-gui-fail rounded-lg transition-colors
                           disabled:opacity-30 disabled:cursor-not-allowed">
              ลบ
            </button>
          </div>
        </div>

        <!-- Permissions: แสดงเฉพาะที่มีสิทธิ์เท่านั้น -->
        <div v-if="!role.permissions?.includes('*')" class="flex flex-wrap gap-2">
          <template v-if="allPermissions.filter(p => role.permissions?.includes(p.key)).length > 0">
            <span
              v-for="p in allPermissions.filter(p => role.permissions?.includes(p.key))"
              :key="p.key"
              class="flex items-center gap-1.5 text-xs rounded-lg px-3 py-1.5
                     bg-gui-in/10 text-gui-in border border-gui-in/20">
              <span>✓</span>
              <span>{{ p.label }}</span>
            </span>
          </template>
          <span v-else class="text-xs text-gui-dim/50 italic">ไม่มีสิทธิ์ใดๆ</span>
        </div>
        <div v-else class="flex flex-wrap gap-2">
          <span v-for="p in allPermissions" :key="p.key"
                class="flex items-center gap-1.5 text-xs rounded-lg px-3 py-1.5
                       bg-gui-in/10 text-gui-in border border-gui-in/20">
            <span>✓</span>
            <span>{{ p.label }}</span>
          </span>
        </div>
      </div>
    </div>

    <!-- ══════════════════════════════════════════════════════════════════════ -->
    <!-- Modals -->
    <!-- ══════════════════════════════════════════════════════════════════════ -->
    <Teleport to="body">

      <!-- Add/Edit User Modal -->
      <div v-if="showUserModal"
           class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
           @click.self="showUserModal = false">
        <div class="bg-gui-panel border border-gui-border rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
          <h3 class="font-bold text-base text-gui-text">
            {{ editingUser ? 'แก้ไขผู้ใช้' : 'เพิ่มผู้ใช้ใหม่' }}
          </h3>

          <div class="space-y-3">
            <div v-if="!editingUser" class="space-y-1">
              <label class="text-xs text-gui-dim uppercase tracking-wide">ชื่อผู้ใช้ (username)</label>
              <input v-model="userForm.username" type="text" placeholder="username"
                     class="input-field" />
            </div>
            <div class="space-y-1">
              <label class="text-xs text-gui-dim uppercase tracking-wide">ชื่อที่แสดง</label>
              <input v-model="userForm.display_name" type="text" placeholder="ชื่อ-นามสกุล"
                     class="input-field" />
            </div>
            <div v-if="!editingUser" class="space-y-1">
              <label class="text-xs text-gui-dim uppercase tracking-wide">รหัสผ่าน</label>
              <input v-model="userForm.password" type="password" placeholder="อย่างน้อย 6 ตัวอักษร"
                     class="input-field" />
            </div>
            <div class="space-y-1">
              <label class="text-xs text-gui-dim uppercase tracking-wide">Role</label>
              <select v-model="userForm.role_id" class="input-field">
                <option v-for="r in roles" :key="r.id" :value="r.id">
                  {{ r.display_name }} ({{ r.name }})
                </option>
              </select>
            </div>
            <div v-if="editingUser" class="flex items-center gap-3">
              <label class="text-xs text-gui-dim uppercase tracking-wide">สถานะ</label>
              <button @click="userForm.is_active = !userForm.is_active"
                      :class="userForm.is_active ? 'bg-gui-in' : 'bg-gui-dim/30'"
                      class="w-10 h-5 rounded-full relative transition-colors shrink-0">
                <span :class="userForm.is_active ? 'translate-x-5' : 'translate-x-0'"
                      class="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full transition-transform shadow" />
              </button>
              <span class="text-xs text-gui-dim">{{ userForm.is_active ? 'ใช้งาน' : 'ระงับ' }}</span>
            </div>
          </div>

          <div v-if="modalError" class="text-xs text-gui-fail bg-gui-fail/10 rounded-lg px-3 py-2">
            {{ modalError }}
          </div>

          <div class="flex gap-2 justify-end pt-2">
            <button @click="showUserModal = false"
                    class="px-4 py-2 text-sm text-gui-dim border border-gui-border rounded-xl hover:border-gui-in/30 transition-colors">
              ยกเลิก
            </button>
            <button @click="saveUser" :disabled="savingUser"
                    class="px-4 py-2 text-sm bg-gui-in/20 border border-gui-in/40 text-gui-in
                           rounded-xl hover:bg-gui-in/30 transition-colors disabled:opacity-50">
              {{ savingUser ? 'กำลังบันทึก...' : 'บันทึก' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Reset Password Modal -->
      <div v-if="showResetModal"
           class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
           @click.self="showResetModal = false">
        <div class="bg-gui-panel border border-gui-border rounded-2xl shadow-2xl w-full max-w-sm p-6 space-y-4">
          <h3 class="font-bold text-base text-gui-text">รีเซ็ตรหัสผ่าน</h3>
          <p class="text-sm text-gui-dim">สำหรับ: <span class="text-gui-text">{{ resetTarget?.display_name }}</span></p>
          <div class="space-y-1">
            <label class="text-xs text-gui-dim uppercase tracking-wide">รหัสผ่านใหม่</label>
            <input v-model="newPassword" type="password" placeholder="อย่างน้อย 6 ตัวอักษร"
                   class="input-field" />
          </div>
          <div v-if="modalError" class="text-xs text-gui-fail bg-gui-fail/10 rounded-lg px-3 py-2">
            {{ modalError }}
          </div>
          <div class="flex gap-2 justify-end">
            <button @click="showResetModal = false"
                    class="px-4 py-2 text-sm text-gui-dim border border-gui-border rounded-xl transition-colors">
              ยกเลิก
            </button>
            <button @click="doResetPassword" :disabled="savingUser"
                    class="px-4 py-2 text-sm bg-yellow-400/20 border border-yellow-400/40 text-yellow-400
                           rounded-xl hover:bg-yellow-400/30 transition-colors disabled:opacity-50">
              {{ savingUser ? 'กำลังรีเซ็ต...' : 'รีเซ็ต' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Add/Edit Role Modal -->
      <div v-if="showRoleModal"
           class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
           @click.self="showRoleModal = false">
        <div class="bg-gui-panel border border-gui-border rounded-2xl shadow-2xl w-full max-w-lg p-6 space-y-4">
          <h3 class="font-bold text-base text-gui-text">
            {{ editingRole ? 'แก้ไข Role' : 'เพิ่ม Role ใหม่' }}
          </h3>

          <div class="space-y-3">
            <div v-if="!editingRole" class="space-y-1">
              <label class="text-xs text-gui-dim uppercase tracking-wide">ชื่อ Role (name)</label>
              <input v-model="roleForm.name" type="text" placeholder="เช่น supervisor"
                     class="input-field" />
            </div>
            <div class="space-y-1">
              <label class="text-xs text-gui-dim uppercase tracking-wide">ชื่อที่แสดง</label>
              <input v-model="roleForm.display_name" type="text" placeholder="เช่น หัวหน้างาน"
                     class="input-field" />
            </div>
            <div class="space-y-2">
              <label class="text-xs text-gui-dim uppercase tracking-wide">Permissions</label>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <label v-for="p in allPermissions" :key="p.key"
                       class="flex items-center gap-3 cursor-pointer px-3 py-2 rounded-xl border transition-colors"
                       :class="roleForm.permissions.includes(p.key)
                         ? 'border-gui-in/40 bg-gui-in/10 text-gui-in'
                         : 'border-gui-border text-gui-dim hover:border-gui-in/20'">
                  <input type="checkbox"
                         :value="p.key"
                         v-model="roleForm.permissions"
                         class="accent-green-400 w-4 h-4" />
                  <span class="text-xs font-medium">{{ p.label }}</span>
                </label>
              </div>
            </div>
          </div>

          <div v-if="modalError" class="text-xs text-gui-fail bg-gui-fail/10 rounded-lg px-3 py-2">
            {{ modalError }}
          </div>

          <div class="flex gap-2 justify-end pt-2">
            <button @click="showRoleModal = false"
                    class="px-4 py-2 text-sm text-gui-dim border border-gui-border rounded-xl hover:border-gui-in/30 transition-colors">
              ยกเลิก
            </button>
            <button @click="saveRole" :disabled="savingRole"
                    class="px-4 py-2 text-sm bg-gui-in/20 border border-gui-in/40 text-gui-in
                           rounded-xl hover:bg-gui-in/30 transition-colors disabled:opacity-50">
              {{ savingRole ? 'กำลังบันทึก...' : 'บันทึก' }}
            </button>
          </div>
        </div>
      </div>

    </Teleport>
  </main>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch, apiPost, apiPut, apiDelete } from '@/api/attendance.js'

const activeTab = ref('users')
const tabs = [
  { key: 'users', label: 'ผู้ใช้' },
  { key: 'roles', label: 'Roles & Permissions' },
]

// ── Data ──────────────────────────────────────────────────────────────────────
const users         = ref([])
const roles         = ref([])
const allPermissions = ref([])
const usersLoading  = ref(false)
const rolesLoading  = ref(false)

async function fetchAll() {
  usersLoading.value = rolesLoading.value = true
  try {
    const [u, r, p] = await Promise.all([
      apiFetch('/admin/users'),
      apiFetch('/admin/roles'),
      apiFetch('/admin/permissions'),
    ])
    users.value        = u
    roles.value        = r
    allPermissions.value = p
  } catch (e) {
    console.error(e)
  } finally {
    usersLoading.value = rolesLoading.value = false
  }
}

onMounted(fetchAll)

// ── User Modal ────────────────────────────────────────────────────────────────
const showUserModal = ref(false)
const editingUser   = ref(null)
const userForm      = ref({ username: '', display_name: '', password: '', role_id: null, is_active: true })
const savingUser    = ref(false)
const modalError    = ref('')

function openAddUser() {
  editingUser.value = null
  userForm.value    = { username: '', display_name: '', password: '', role_id: roles.value[0]?.id || null, is_active: true }
  modalError.value  = ''
  showUserModal.value = true
}
function openEditUser(u) {
  editingUser.value = u
  userForm.value    = { display_name: u.display_name, role_id: u.role_id, is_active: u.is_active }
  modalError.value  = ''
  showUserModal.value = true
}
async function saveUser() {
  modalError.value = ''
  savingUser.value = true
  try {
    if (editingUser.value) {
      await apiPut(`/admin/users/${editingUser.value.id}`, {
        display_name: userForm.value.display_name,
        role_id:      userForm.value.role_id,
        is_active:    userForm.value.is_active,
      })
    } else {
      await apiPost('/admin/users', userForm.value)
    }
    showUserModal.value = false
    await fetchAll()
  } catch (e) {
    modalError.value = e.message
  } finally {
    savingUser.value = false
  }
}

async function confirmDeleteUser(u) {
  if (!confirm(`ลบผู้ใช้ "${u.display_name}" (@${u.username}) ?\nการดำเนินการนี้ไม่สามารถยกเลิกได้`)) return
  try {
    await apiDelete(`/admin/users/${u.id}`)
    await fetchAll()
  } catch (e) {
    alert(e.message)
  }
}

// ── Reset Password ────────────────────────────────────────────────────────────
const showResetModal = ref(false)
const resetTarget    = ref(null)
const newPassword    = ref('')

function openResetPassword(u) {
  resetTarget.value  = u
  newPassword.value  = ''
  modalError.value   = ''
  showResetModal.value = true
}
async function doResetPassword() {
  modalError.value = ''
  savingUser.value = true
  try {
    await apiPost(`/admin/users/${resetTarget.value.id}/reset-password`, {
      new_password: newPassword.value,
    })
    showResetModal.value = false
  } catch (e) {
    modalError.value = e.message
  } finally {
    savingUser.value = false
  }
}

// ── Role Modal ────────────────────────────────────────────────────────────────
const showRoleModal = ref(false)
const editingRole   = ref(null)
const roleForm      = ref({ name: '', display_name: '', permissions: [] })
const savingRole    = ref(false)

function openAddRole() {
  editingRole.value = null
  roleForm.value    = { name: '', display_name: '', permissions: [] }
  modalError.value  = ''
  showRoleModal.value = true
}
function openEditRole(r) {
  editingRole.value = r
  roleForm.value    = {
    display_name: r.display_name,
    permissions:  r.permissions?.includes('*') ? [] : [...(r.permissions || [])],
  }
  modalError.value  = ''
  showRoleModal.value = true
}
async function saveRole() {
  modalError.value = ''
  savingRole.value = true
  try {
    if (editingRole.value) {
      await apiPut(`/admin/roles/${editingRole.value.id}`, {
        display_name: roleForm.value.display_name,
        permissions:  roleForm.value.permissions,
      })
    } else {
      await apiPost('/admin/roles', roleForm.value)
    }
    showRoleModal.value = false
    await fetchAll()
  } catch (e) {
    modalError.value = e.message
  } finally {
    savingRole.value = false
  }
}

async function confirmDeleteRole(r) {
  if (!confirm(`ลบ Role "${r.display_name}" ?`)) return
  try {
    await apiDelete(`/admin/roles/${r.id}`)
    await fetchAll()
  } catch (e) {
    alert(e.message)
  }
}
</script>

<style scoped>
.input-field {
  @apply w-full bg-gui-bg border border-gui-border rounded-xl px-4 py-2.5
         text-sm text-gui-text placeholder-gui-dim/50
         focus:outline-none focus:border-gui-in/60 focus:ring-1 focus:ring-gui-in/30
         transition-colors;
}
</style>
