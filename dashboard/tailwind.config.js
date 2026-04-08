// ─────────────────────────────────────────────────────────────────────
// tailwind.config.js — สีและ theme ให้ match กับ OpenCV GUI เดิม
// ─────────────────────────────────────────────────────────────────────

/** @type {import('tailwindcss').Config} */
export default {
  // Scan เฉพาะไฟล์ใน src/ เพื่อ purge CSS ที่ไม่ได้ใช้
  content: ['./index.html', './src/**/*.{vue,js,ts}'],

  theme: {
    extend: {
      colors: {
        // ── สีหลัก (ดึงมาจาก config.py / config_pi5.py ของ GUI เดิม) ──
        //    เปลี่ยนสีได้ที่นี่ที่เดียว แล้ว component ทุกตัวจะอัพเดตตาม
        'gui-bg':     '#0d1117',   // พื้นหลังหลัก (เข้มกว่า PANEL_BG เล็กน้อย)
        'gui-panel':  '#161b22',   // panel / card background
        'gui-border': '#30363d',   // เส้นขอบ
        'gui-in':     '#00dc00',   // CHECKED_IN ── เขียว (ตรงกับ GUI)
        'gui-out':    '#ffd700',   // OUT / LIVENESS ── เหลือง (ตรงกับ GUI)
        'gui-fail':   '#ff3333',   // FAIL / UNKNOWN ── แดง
        'gui-warn':   '#ff6600',   // LIVENESS_FAIL ── ส้ม
        'gui-text':   '#e6edf3',   // ข้อความหลัก
        'gui-dim':    '#7d8590',   // ข้อความรอง / label
      },

      fontFamily: {
        // Sarabun รองรับภาษาไทยได้ดี ถ้าไม่มี Sarabun จะ fallback เป็น system font
        sans: ['Sarabun', 'Noto Sans Thai', 'system-ui', 'sans-serif'],
      },

      animation: {
        // animation ช้าสำหรับ indicator dot
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },

  plugins: [],
}
