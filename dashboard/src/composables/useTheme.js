import { ref } from 'vue'

const STORAGE_KEY = 'face-dashboard-theme'

// module-level reactive state
const theme = ref(localStorage.getItem(STORAGE_KEY) ?? 'auto')

/** ตรวจว่าเวลาปัจจุบันอยู่ในช่วงกลางวัน (06:00–18:00) หรือเปล่า */
function isDaytime() {
  const h = new Date().getHours()
  return h >= 6 && h < 18   // 06:00–17:59 = กลางวัน
}

function applyTheme(t) {
  const isDark = t === 'dark' || (t === 'auto' && !isDaytime())
  document.documentElement.classList.toggle('dark', isDark)
}

// apply ทันทีตอน import
applyTheme(theme.value)

// ฟังก์ชัน set theme — เรียกตรงๆ ทันที
export function setTheme(t) {
  theme.value = t
  applyTheme(t)
  localStorage.setItem(STORAGE_KEY, t)
}

// ── Auto loop: ตรวจเวลาทุก 60 วินาที (สำหรับ mode auto) ──────────
// โปรแกรมทำงานตลอด → ต้องเช็คว่าข้ามช่วง 06:00 หรือ 18:00 แล้วหรือยัง
setInterval(() => {
  if (theme.value === 'auto') applyTheme('auto')
}, 60_000)

export function useTheme() {
  return { theme, setTheme }
}
