import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,   // bind 0.0.0.0 — เข้า dev server จากเครื่องอื่นได้
    port: 5180,   // dev ใช้พอร์ตคนละชุดกับ Jetson (5180/8010/8011) กัน VS Code port-forward ชน
    proxy: {
      '/attendance': {
        target: 'http://localhost:8010',
        changeOrigin: true,
      },
      '/person': {
        target: 'http://localhost:8010',
        changeOrigin: true,
      },
      // ใช้ /api prefix แล้ว rewrite ตัดออกก่อน forward — กัน path ชนกับ React Router
      '/api': {
        target: 'http://localhost:8010',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/stream': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/snapshot': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/status': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/state': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/snap': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/window': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/cameras': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/system': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/cache': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/snapfull': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/push': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/auth': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/users': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
      '/audit': {
        target: 'http://localhost:8011',
        changeOrigin: true,
      },
    },
  },
})
