/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: { 300:'#93c5fd',400:'#60a5fa',500:'#3b82f6',600:'#2563eb',700:'#1d4ed8',800:'#1e40af',900:'#1e3a8a',950:'#172554' },
        surface: { DEFAULT:'#0f172a', card:'#1e293b', elevated:'#334155', border:'#475569' },
      },
      fontFamily: { sans: ['Inter','system-ui','sans-serif'], mono: ['JetBrains Mono','monospace'] },
      animation: { 'fade-in': 'fadeIn 0.3s ease-in-out' },
      keyframes: { fadeIn: { from: { opacity: '0' }, to: { opacity: '1' } } },
    },
  },
  plugins: [],
}
