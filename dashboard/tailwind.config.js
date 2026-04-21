// ─────────────────────────────────────────────────────────────────────
// tailwind.config.js — สีและ theme ให้ match กับ OpenCV GUI เดิม
// ─────────────────────────────────────────────────────────────────────

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],

  // ใช้ class strategy เพื่อให้ Vue toggle dark mode ได้
  darkMode: 'class',

  theme: {
    extend: {
      colors: {
        // ── สีปรับตาม theme (ผ่าน CSS variables) ──────────────────────
        // ใช้ rgb(var(--name) / <alpha-value>) เพื่อรองรับ /opacity modifier
        'gui-bg':     'rgb(var(--gui-bg)     / <alpha-value>)',
        'gui-panel':  'rgb(var(--gui-panel)  / <alpha-value>)',
        'gui-border': 'rgb(var(--gui-border) / <alpha-value>)',
        'gui-text':   'rgb(var(--gui-text)   / <alpha-value>)',
        'gui-dim':    'rgb(var(--gui-dim)    / <alpha-value>)',

        // ── สีฟังก์ชัน (ปรับตาม theme เพื่อ contrast ที่ดีทั้ง light/dark) ──
        'gui-in':   'rgb(var(--gui-in)   / <alpha-value>)',
        'gui-out':  'rgb(var(--gui-out)  / <alpha-value>)',
        'gui-fail': 'rgb(var(--gui-fail) / <alpha-value>)',
        'gui-warn': 'rgb(var(--gui-warn) / <alpha-value>)',
      },

      fontFamily: {
        sans: ['Sarabun', 'Noto Sans Thai', 'system-ui', 'sans-serif'],
      },

      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },

  plugins: [],
}
