import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { readFileSync } from 'node:fs';

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as { version: string };

// Hem tarayıcıda hem Tauri masaüstü kabuğunda (macOS WKWebView) çalışır.
export default defineConfig({
  plugins: [react()],
  define: {
    // Uygulamada gösterilen ve güncelleme kontrolünde karşılaştırılan sürüm.
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // Tauri CLI'nin kendi çıktısı silinmesin.
  clearScreen: false,
  server: {
    // tauri.conf.json içindeki devUrl ile aynı; port doluysa sessizce başka porta kaçmasın.
    port: 5173,
    strictPort: true,
  },
  build: {
    // macOS 11 (uygulamanın asgari sürümü) Safari 14 ile gelir.
    target: ['es2020', 'safari14'],
  },
});
