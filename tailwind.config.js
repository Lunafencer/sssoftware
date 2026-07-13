/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx,js,jsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        primary: 'var(--color-primary)',
        'primary-2': 'var(--color-primary-2)',
        accent: 'var(--color-accent)',
        'accent-2': 'var(--color-accent-2)',
        ai: 'var(--color-ai)',
        success: 'var(--color-success)',
        warning: 'var(--color-warning)',
        danger: 'var(--color-danger)',
        bg: 'var(--color-bg)',
        card: 'var(--color-card)',
        border: 'var(--color-border)',
        text: 'var(--color-text)',
        'text-2': 'var(--color-text-2)',
        'on-dark': 'var(--color-on-dark)'
      },
      borderRadius: {
        card: 'var(--radius-card)',
        btn: 'var(--radius-btn)'
      },
      fontFamily: {
        sans: ['Inter', '"Source Han Sans CN"', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'DIN', 'Menlo', 'Consolas', 'monospace']
      },
      boxShadow: {
        card: '0 1px 2px rgba(11,37,69,0.04), 0 0 0 1px var(--color-border)',
        float: '0 8px 24px rgba(11,37,69,0.12)'
      }
    }
  },
  plugins: []
}
