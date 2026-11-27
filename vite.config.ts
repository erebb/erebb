import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Hem tarayıcıda hem Tauri masaüstü kabuğunda (macOS WKWebView) çalışır.
export default defineConfig({
  plugins: [react()],
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
  envPrefix: ['VITE_', 'TAURI_ENV_'],
  build: {
    // macOS 11 (uygulamanın asgari sürümü) Safari 14 ile gelir.
    target: ['es2020', 'safari14'],
  },
});
