/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 主色调 - 闲鱼黄色系
        primary: {
          50: '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
          800: '#92400e',
          900: '#78350f',
        },
        // 闲鱼橙色点缀
        xianyu: {
          light: '#fff7ed',
          DEFAULT: '#ff6600',
          dark: '#ea580c',
        },
        // 背景色
        background: {
          DEFAULT: '#f8fafc',
          secondary: '#ffffff',
          tertiary: '#f1f5f9',
        },
        // 边框色
        border: {
          DEFAULT: '#e2e8f0',
          light: '#f1f5f9',
        },
        // 文字色
        foreground: {
          DEFAULT: '#1e293b',
          secondary: '#64748b',
          muted: '#94a3b8',
        },
      },
      borderRadius: {
        'ios': '20px',
        'ios-lg': '24px',
        'ios-xl': '28px',
      },
      boxShadow: {
        'ios': '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05)',
        'ios-md': '0 8px 16px -4px rgba(0, 0, 0, 0.08), 0 4px 8px -4px rgba(0, 0, 0, 0.04)',
        'ios-lg': '0 12px 24px -6px rgba(0, 0, 0, 0.1), 0 6px 12px -6px rgba(0, 0, 0, 0.05)',
        'glass': '0 8px 32px rgba(0, 0, 0, 0.08), inset 0 1px 0 0 rgba(255, 255, 255, 0.6)',
      },
      backdropBlur: {
        'ios': '20px',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'scale-in': 'scaleIn 0.2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
    },
  },
  plugins: [],
}
