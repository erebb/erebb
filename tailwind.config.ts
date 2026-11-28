import type { Config } from 'tailwindcss';

/**
 * Odak teması. Renkler `src/index.css`'teki CSS değişkenlerinden gelir (açık / koyu tema).
 * `duo-*` adları tarihseldir; anlamları:
 * - duo-gray-50 sayfa zemini · 100 çizgi/iz · 300 sönük metin · 500 ikincil metin · 700 ana metin · 900 en koyu
 * - surface: kart/panel yüzeyi
 * - duo-blue: tek vurgu rengi (ana düğme, seçim, odak halkası)
 * - duo-green: yalnız "doğru" geri bildirimi · duo-red: yalnız "yanlış" · duo-gold: "Sınavda" vurgusu
 *   Her rengin DEFAULT'u dolgu (üstünde beyaz yazı okunur), `dark`'ı yüzey üstünde metin,
 *   `light`'ı hafif renkli zemindir. Koyu temada `dark` açık tona döner, adı değil rolü önemli.
 * - ink: Akış'ın temadan bağımsız koyu sahnesi
 */
const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;
const tone = (name: string) => ({ DEFAULT: v(name), dark: v(`${name}-strong`), light: v(`${name}-soft`) });

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: v('surface'),
        'duo-green': tone('green'),
        'duo-blue': tone('blue'),
        'duo-gold': tone('gold'),
        'duo-red': tone('red'),
        'duo-gray': {
          50: v('gray-50'),
          100: v('gray-100'),
          300: v('gray-300'),
          500: v('gray-500'),
          700: v('gray-700'),
          900: v('gray-900'),
        },
        ink: { DEFAULT: '#15181C', deep: '#0E1013', 2: '#1D2126', 3: '#272C33' },
      },
      borderRadius: {
        xl: '0.75rem',
        '2xl': '1rem',
      },
      boxShadow: {
        'duo-card': 'var(--shadow-card)',
      },
      fontFamily: {
        sans: [
          '"Atkinson Hyperlegible Next"',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          '"Segoe UI"',
          'sans-serif',
        ],
      },
      maxWidth: {
        // Okuma satırı: satır başına ~65–75 karakter.
        measure: '68ch',
      },
      keyframes: {
        'flash-correct': {
          '0%,100%': { backgroundColor: 'transparent' },
          '50%': { backgroundColor: 'rgb(var(--green) / 0.08)' },
        },
        'flash-incorrect': {
          '0%,100%': { backgroundColor: 'transparent' },
          '50%': { backgroundColor: 'rgb(var(--red) / 0.08)' },
        },
        'pop-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'flash-correct': 'flash-correct 0.3s ease-out',
        'flash-incorrect': 'flash-incorrect 0.3s ease-out',
        'pop-in': 'pop-in 0.15s ease-out',
      },
    },
  },
  plugins: [],
} satisfies Config;
