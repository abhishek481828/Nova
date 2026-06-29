/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cyber: {
          bg: '#000000',
          panel: 'rgba(10, 15, 30, 0.45)',
          panelBorder: 'rgba(56, 189, 248, 0.15)',
          glowCyan: '#00f2fe',
          glowBlue: '#4facfe',
          text: '#e2e8f0',
          muted: '#94a3b8',
        }
      },
      fontFamily: {
        sans: ['Outfit', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        'cyan-glow': '0 0 15px rgba(0, 242, 254, 0.3)',
        'blue-glow': '0 0 15px rgba(79, 172, 254, 0.3)',
      }
    },
  },
  plugins: [],
}
