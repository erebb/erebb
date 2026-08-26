import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'duo-green': { DEFAULT: '#58CC02', dark: '#46A302', light: '#D7FFB8' },
        'duo-blue': { DEFAULT: '#1CB0F6', dark: '#1899D6', light: '#DDF4FF' },
        'duo-gold': { DEFAULT: '#FFC800', dark: '#E6B400', light: '#FFF4D1' },
        'duo-red': { DEFAULT: '#FF4B4B', dark: '#EA2B2B', light: '#FFDFE0' },
        'duo-gray': {
          50: '#F7F7F7',
          100: '#E5E5E5',
          300: '#AFAFAF',
          500: '#777777',
          700: '#4B4B4B',
          900: '#3C3C3C',
        },
      },
      borderRadius: {
        xl: '1rem',
        '2xl': '1.25rem',
      },
      boxShadow: {
        'duo-btn': '0 4px 0 0 #46A302',
        'duo-btn-blue': '0 4px 0 0 #1899D6',
        'duo-btn-red': '0 4px 0 0 #EA2B2B',
        'duo-btn-gray': '0 4px 0 0 #E5E5E5',
        'duo-btn-flat': '0 1px 0 0 #46A302',
        'duo-card': '0 2px 0 0 #E5E5E5',
      },
      fontFamily: {
        sans: ['"Nunito"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        'flash-correct': {
          '0%,100%': { backgroundColor: 'transparent' },
          '50%': { backgroundColor: 'rgb(88 204 2 / 0.15)' },
        },
        'flash-incorrect': {
          '0%,100%': { backgroundColor: 'transparent' },
          '50%': { backgroundColor: 'rgb(255 75 75 / 0.15)' },
        },
        'pop-in': {
          '0%': { transform: 'scale(0.8)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
      },
      animation: {
        'flash-correct': 'flash-correct 0.4s ease-out',
        'flash-incorrect': 'flash-incorrect 0.4s ease-out',
        'pop-in': 'pop-in 0.25s ease-out',
      },
    },
  },
  plugins: [],
} satisfies Config;
