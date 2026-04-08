// ─────────────────────────────────────────────────────────────────────
// main.js — จุดเริ่มต้นของ Vue 3 App
// ─────────────────────────────────────────────────────────────────────
import { createApp } from 'vue'
import App    from './App.vue'
import router from './router/index.js'
import './style.css'

createApp(App)
  .use(router)   // ลงทะเบียน vue-router
  .mount('#app')
