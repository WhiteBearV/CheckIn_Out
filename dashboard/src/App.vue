<template>
  <!--
    App.vue — Layout Shell หลักของทั้ง App
    ────────────────────────────────────────
    ทุกหน้าจะมี AppHeader + AppNav + footer เหมือนกัน
    เนื้อหาของแต่ละหน้าแสดงผ่าน <RouterView />

    เพิ่มหน้าใหม่: แก้ router/index.js และ AppNav จะอัพเดตเอง
  -->
  <div class="min-h-screen flex flex-col">

    <!-- ── Header (clock / title) ─────────────────────── -->
    <AppHeader />

    <!-- ── Tab Navigation ────────────────────────────── -->
    <AppNav />

    <!-- ── Page Content ──────────────────────────────── -->
    <!-- แต่ละหน้า (DashboardView / CameraView) render ที่นี่ -->
    <RouterView class="flex-1" />

    <!-- ── Footer ────────────────────────────────────── -->
    <footer class="text-center text-xs text-gui-dim py-3
                   border-t border-gui-border shrink-0">
      Face Attendance Dashboard
      <span class="ml-2 opacity-50">v1.11.0</span>
    </footer>

  </div>
</template>

<script setup>
import { RouterView } from 'vue-router'
import AppHeader from '@/components/AppHeader.vue'
import AppNav    from '@/components/AppNav.vue'
</script>
