import { createRouter, createWebHashHistory } from 'vue-router'
import { isAuthenticated, checkTokenExpiry, hasPermission } from '@/composables/useAuth.js'
import CameraView       from '@/views/CameraView.vue'
import DashboardView    from '@/views/DashboardView.vue'
import SingleCameraView from '@/views/SingleCameraView.vue'
import LoginView        from '@/views/LoginView.vue'
import SettingsView     from '@/views/SettingsView.vue'
import HistoryView      from '@/views/HistoryView.vue'

const routes = [
  {
    path:      '/login',
    name:      'login',
    component: LoginView,
    meta:      { public: true },
  },
  {
    path:      '/',
    name:      'dashboard',
    component: CameraView,
    meta: {
      label:      'กล้อง',
      icon:       '📷',
      permission: 'cameras.view',
    },
  },
  {
    path:      '/overview',
    name:      'overview',
    component: DashboardView,
    meta: {
      label:      'ภาพรวม',
      icon:       '📊',
      permission: 'attendance.view',
    },
  },
  {
    path:      '/camera/:camId',
    name:      'camera-detail',
    component: SingleCameraView,
    meta:      { permission: 'cameras.view' },
  },
  {
    path:      '/history',
    name:      'history',
    component: HistoryView,
    meta: {
      label:      'ประวัติ',
      icon:       '📋',
      permission: 'attendance.view',
    },
  },
  {
    path:      '/settings',
    name:      'settings',
    component: SettingsView,
    meta: {
      label:      'ตั้งค่า',
      icon:       '⚙',
      permission: 'users.manage',
    },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta.public) return true

  // ตรวจ token หมดอายุ
  if (!checkTokenExpiry() || !isAuthenticated.value) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // ตรวจ permission (ถ้า route ต้องการ)
  if (to.meta.permission && !hasPermission(to.meta.permission)) {
    // ไปหน้าแรกที่มีสิทธิ์
    return { name: 'dashboard' }
  }

  return true
})

export default router
