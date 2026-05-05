import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/attendance': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/person': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // ใช้ /api prefix แล้ว rewrite ตัดออกก่อน forward — กัน path ชนกับ React Router
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/stream': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/snapshot': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/status': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/state': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/snap': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/window': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/cameras': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/system': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/cache': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/snapfull': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/push': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/auth': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
