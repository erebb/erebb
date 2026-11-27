import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// Nunito pakete gömülü: masaüstü uygulaması internetsiz açılır, Google Fonts'a gidilmez.
// Yalnız latin + latin-ext alt kümeleri — Türkçe ğ ş ı İ latin-ext'tedir.
import '@fontsource/nunito/latin-400.css';
import '@fontsource/nunito/latin-ext-400.css';
import '@fontsource/nunito/latin-600.css';
import '@fontsource/nunito/latin-ext-600.css';
import '@fontsource/nunito/latin-700.css';
import '@fontsource/nunito/latin-ext-700.css';
import '@fontsource/nunito/latin-800.css';
import '@fontsource/nunito/latin-ext-800.css';
import '@fontsource/nunito/latin-900.css';
import '@fontsource/nunito/latin-ext-900.css';

import './index.css';
import { prepareStorage } from './content/seed';

// Eski verileri taşı ve uygulamayla gelen ders paketlerini (ilk açılışta bir kez) ekle.
// Çizimden önce beklenir; sağlayıcılar başlangıç durumunu LocalStorage'dan okur.
void prepareStorage().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});
