import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// Atkinson Hyperlegible Next (Braille Institute): harfleri birbirinden ayırt edilmek için
// tasarlanmış okunaklılık yazı tipi — I/l/1, O/0, rn/m karışmaz; ilaç ve terim adlarında işe yarar.
// Pakete gömülü: uygulama internetsiz açılır. Her ağırlık latin + latin-ext (ğ ş İ) içerir.
import '@fontsource/atkinson-hyperlegible-next/400.css';
import '@fontsource/atkinson-hyperlegible-next/500.css';
import '@fontsource/atkinson-hyperlegible-next/600.css';
import '@fontsource/atkinson-hyperlegible-next/700.css';

import './index.css';
import { prepareStorage } from './content/seed';
import { applyTheme, readThemePref } from './lib/display';

// Tema ilk çizimden önce: koyu temada beyaz parlama olmasın.
applyTheme(readThemePref());

// Eski verileri taşı ve uygulamayla gelen ders paketlerini (ilk açılışta bir kez) ekle.
// Çizimden önce beklenir; sağlayıcılar başlangıç durumunu LocalStorage'dan okur.
void prepareStorage().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});
