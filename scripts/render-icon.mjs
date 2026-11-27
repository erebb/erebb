// Uygulama ikonunu SVG'den PNG'ye çevirir (Tauri `tauri icon` komutu için 1024×1024 kaynak).
// Kullanım: node scripts/render-icon.mjs src-tauri/app-icon.svg src-tauri/app-icon.png [boyut]
// PW_CHROMIUM_PATH ayarlıysa o Chromium kullanılır; yoksa Playwright'ın kendi tarayıcısı.
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';

const [, , svgPath, outPath, sizeArg = '1024'] = process.argv;
if (!svgPath || !outPath) {
  console.error('Kullanım: node scripts/render-icon.mjs <girdi.svg> <çıktı.png> [boyut]');
  process.exit(1);
}
const size = Number(sizeArg);
const svg = readFileSync(svgPath, 'utf8').replace(
  'width="1024" height="1024"',
  `width="${size}" height="${size}"`
);

const browser = await chromium.launch(
  process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {}
);
const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
await page.setContent(`<html><body style="margin:0;background:transparent">${svg}</body></html>`);
await page.screenshot({
  path: outPath,
  omitBackground: true,
  clip: { x: 0, y: 0, width: size, height: size },
});
await browser.close();
console.log('yazıldı:', outPath);
