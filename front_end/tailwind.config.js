/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Sarabun', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      colors: {
        void:  '#0f0f0f',
        cyan:  '#00ffff',
        brand: '#0007cd',
      },
      borderColor: {
        'mist-10': 'rgba(255,255,255,0.10)',
        'mist-06': 'rgba(255,255,255,0.06)',
        'mist-04': 'rgba(255,255,255,0.04)',
      },
    },
  },
  plugins: [],
}
