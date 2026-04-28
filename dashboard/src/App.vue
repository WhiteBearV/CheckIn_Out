<template>
  <!--
    App.vue — Layout Shell หลักของทั้ง App
    ────────────────────────────────────────
    ทุกหน้าจะมี AppHeader + AppNav + footer เหมือนกัน
    เนื้อหาของแต่ละหน้าแสดงผ่าน <RouterView />

    เพิ่มหน้าใหม่: แก้ router/index.js และ AppNav จะอัพเดตเอง
  -->
  <div class="min-h-screen flex flex-col">

    <!-- ── Header / Nav / Footer ซ่อนเมื่อ fullscreen ── -->
    <AppHeader v-show="!isUIFullscreen" />
    <AppNav    v-show="!isUIFullscreen" />

    <!-- ── Page Content ──────────────────────────────── -->
    <RouterView :class="isUIFullscreen ? 'flex-1 h-screen' : 'flex-1'" />

    <footer
      v-show="!isUIFullscreen"
      class="text-center text-xs text-gui-dim py-3 border-t border-gui-border shrink-0"
    >
      Face Attendance Dashboard
      <span class="ml-2 opacity-50">v1.11.0</span>
    </footer>

  </div>
</template>

<script setup>
import { RouterView } from 'vue-router'
import AppHeader from '@/components/AppHeader.vue'
import AppNav    from '@/components/AppNav.vue'
import { isUIFullscreen } from '@/composables/useUIFullscreen.js'
</script>
