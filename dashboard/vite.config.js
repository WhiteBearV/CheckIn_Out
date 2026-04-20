// ─────────────────────────────────────────────────────────────────────
// vite.config.js — Vite build & dev server config
// ─────────────────────────────────────────────────────────────────────
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],

  resolve: {
    // alias @/ → src/  ใช้ import ได้สั้นกว่า เช่น import X from '@/components/X.vue'
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },

  server: {
    port: 5173,   // ← เปลี่ยน port dev server ได้ที่นี่

    proxy: {
      // ── Dev Proxy ────────────────────────────────────────────────────
      // request ที่ขึ้นต้นด้วย /api จะถูกส่งต่อไป FastAPI (port 8000)
      // ตัด prefix /api ออกก่อนส่ง → /api/attendance/today → /attendance/today
      //
      // ถ้า FastAPI รันพอร์ตอื่น: เปลี่ยน target ด้านล่าง
      // ถ้า FastAPI อยู่เครื่องอื่น: เปลี่ยน localhost เป็น IP นั้น
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },

  build: {
    // output ไปที่ ../static/ เพื่อให้ FastAPI เสิร์ฟได้ตรงๆ
    // ถ้าไม่ต้องการ serve จาก FastAPI ลบ outDir บรรทัดนี้ออก
    outDir: '../static',
    emptyOutDir: true,
  },

  // base path ต้องตรงกับที่ FastAPI mount ไว้ (/dashboard/)
  base: '/dashboard/',
})
