<template>
  <!--
    AppNav.vue — แถบเมนูนำทาง (Tab Navigation)
    ─────────────────────────────────────────────
    แสดง link ไปยังแต่ละหน้าโดยอ่าน route meta.label / meta.icon
    เมนู active จะมีเส้นขีดเขียวด้านล่างและข้อความสว่างกว่า

    เพิ่มเมนูใหม่: เพิ่ม route ใน router/index.js เท่านั้น
                   AppNav จะแสดงโดยอัตโนมัติ
  -->
  <nav class="bg-gui-panel border-b border-gui-border px-4
              flex items-center gap-1 shrink-0">

    <RouterLink
      v-for="route in menuRoutes"
      :key="route.name"
      :to="route.path"
      class="flex items-center gap-1.5 px-4 py-3 text-sm
             border-b-2 transition-colors"
      :class="isActive(route)
        ? 'border-gui-in text-gui-text font-medium'
        : 'border-transparent text-gui-dim hover:text-gui-text hover:border-gui-border'"
    >
      <span>{{ route.meta.icon }}</span>
      <span>{{ route.meta.label }}</span>
    </RouterLink>

  </nav>
</template>

<script setup>
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route  = useRoute()

// ดึงเฉพาะ routes ที่มี meta.label (ที่ต้องการแสดงในเมนู)
const menuRoutes = router.getRoutes().filter(r => r.meta?.label)

// ตรวจว่า route นั้น active อยู่หรือเปล่า
function isActive(r) {
  return route.name === r.name
}
</script>
