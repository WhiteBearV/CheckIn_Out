// ─────────────────────────────────────────────────────────────────────
// router/index.js — Vue Router config
//
// เพิ่มหน้าใหม่:
//   1. import component ที่ต้องการ
//   2. เพิ่ม object ใน routes array
//   3. เพิ่ม link ใน AppNav.vue
// ─────────────────────────────────────────────────────────────────────

import { createRouter, createWebHashHistory } from 'vue-router'
import CameraView       from '@/views/CameraView.vue'
import SingleCameraView from '@/views/SingleCameraView.vue'

// ── Route definitions ─────────────────────────────────────────────
const routes = [
  {
    path:      '/',
    name:      'dashboard',
    component: CameraView,
    meta: {
      label: 'หน้าหลัก',
      icon:  '📷',
    },
  },
  {
    path:      '/cctv',
    name:      'cctv',
    component: CameraView,
    meta: {
      label: 'โหมด CCTV',
      icon:  '🖥',
      cctv:  true,   // trigger isFullscreen อัตโนมัติใน CameraView
    },
  },
  {
    path:      '/camera/:camId',
    name:      'camera-detail',
    component: SingleCameraView,
    // ไม่ใส่ meta.label เพื่อไม่ให้แสดงใน AppNav
  },
  // ── เพิ่ม route ใหม่ที่นี่ ──────────────────────────────────────
]

// ── Create router ─────────────────────────────────────────────────
// ใช้ Hash history (#/) เพื่อรองรับ serve จาก FastAPI StaticFiles
// โดยไม่ต้องตั้งค่า server-side routing เพิ่มเติม
const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
