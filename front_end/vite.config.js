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
    },
  },
})
