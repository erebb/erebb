// Kelime Ustası — uçtan uca duman testi.
//
// Üretim derlemesini (dist/) `vite preview` ile sunar ve uygulamanın ana akışlarını gerçek
// bir tarayıcı motorunda sürer. CI'da macOS üzerinde WebKit ile koşar — masaüstü
// uygulamasının kullandığı WKWebView ile aynı motor.
//
// Ortam değişkenleri:
//   E2E_BROWSER      chromium | webkit | firefox   (varsayılan: chromium)
//   PW_CHROMIUM_PATH (isteğe bağlı) Belirli bir Chromium çalıştırılabilir dosyası
//   E2E_SCREENSHOTS  Ekran görüntülerinin yazılacağı klasör (isteğe bağlı)
//
// Masaüstü uygulamasının CSP'si tauri.conf.json'dan okunup her belgeye uygulanır;
// böylece "tarayıcıda çalışıyor ama uygulamada CSP yüzünden bozuk" durumu yakalanır.

import { spawn } from 'node:child_process';
import { readFileSync, mkdirSync } from 'node:fs';
import { chromium, webkit, firefox } from 'playwright';

const BROWSER = process.env.E2E_BROWSER ?? 'chromium';
const PORT = 4173;
const URL = `http://localhost:${PORT}`;
const SHOTS = process.env.E2E_SCREENSHOTS;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

const readJson = (rel) => JSON.parse(readFileSync(new globalThis.URL(rel, import.meta.url)));
const CSP = readJson('../src-tauri/tauri.conf.json').app.security.csp;

// Uygulamayla gelen içerik — doğru cevapları bilmek için.
const H7 = readJson('../content/mikrobiyoloji-hafta-7.json');
const H8 = readJson('../content/mikrobiyoloji-hafta-8.json');
const ANSWER = new Map(); // soru kökü / kart önü → doğru cevap
for (const pack of [H7, H8]) {
  for (const it of pack.items) ANSWER.set((it.question ?? it.front).trim(), (it.answer ?? it.back).trim());
}
const count = (pack, type) => pack.items.filter((i) => i.type === type).length;
const H7_MCQ = count(H7, 'mcq');
const H7_CARDS = count(H7, 'card');
const H8_MCQ = count(H8, 'mcq');
const TOTAL_MCQ = H7_MCQ + H8_MCQ;
const TOTAL_CARDS = H7_CARDS + count(H8, 'card');
const TOPO_SETS = ['damarlar', 'lenf', 'sinirler', 'govde', 'klinik'].map((k) => readJson(`../content/topografik-${k}.json`));
const TOPO_DAMAR = TOPO_SETS[0];
const MANIFEST = readJson('../content/manifest.json');
const PKG_VERSION = readJson('../package.json').version;
const H8_ITEMS = H8.items.length;
const CORS = { 'access-control-allow-origin': '*' };

// ---------------------------------------------------------------------------

const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
}

function stopPreview(proc) {
  try {
    // npx → vite: yalnızca npx'i öldürmek vite'ı açık bırakır (port dolu kalır, betik kapanmaz).
    if (process.platform !== 'win32') process.kill(-proc.pid, 'SIGTERM');
    else proc.kill();
  } catch {
    proc.kill();
  }
}

async function startPreview() {
  const proc = spawn('npx', ['vite', 'preview', '--port', String(PORT), '--strictPort'], {
    stdio: ['ignore', 'pipe', 'pipe'],
    // Kendi süreç grubunda: npx'in başlattığı vite alt süreci de birlikte kapatılabilsin.
    detached: process.platform !== 'win32',
  });
  let log = '';
  proc.stdout.on('data', (d) => (log += d));
  proc.stderr.on('data', (d) => (log += d));
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(URL);
      if (r.ok) return proc;
    } catch {
      /* henüz ayağa kalkmadı */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  stopPreview(proc);
  throw new Error(`vite preview başlamadı:\n${log}`);
}

async function launch() {
  const engines = { chromium, webkit, firefox };
  const engine = engines[BROWSER];
  if (!engine) throw new Error(`Bilinmeyen E2E_BROWSER: ${BROWSER}`);
  const opts =
    BROWSER === 'chromium' && process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {};
  return engine.launch(opts);
}

async function newPage(browser, viewport) {
  const ctx = await browser.newContext({ viewport, hasTouch: BROWSER !== 'firefox' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console: ${m.text()}`);
  });
  // Masaüstü uygulamasının CSP'sini her HTML yanıtına ekle.
  await page.route('**/*', async (route) => {
    const req = route.request();
    if (req.resourceType() !== 'document') return route.continue();
    const res = await route.fetch();
    await route.fulfill({ response: res, headers: { ...res.headers(), 'content-security-policy': CSP } });
  });
  // Açılıştaki güncelleme denetimi: GitHub'a gitme, "sürüm yok" de. Sonra kaydedilen route
  // önce çalışır; testler kendi sahte sürümlerini bunun üstüne kaydedebilir.
  await page.route(
    (url) => url.hostname === 'api.github.com' || url.hostname === 'raw.githubusercontent.com',
    (route) => route.fulfill({ status: 200, contentType: 'application/json', headers: CORS, body: '{}' })
  );
  await page.addInitScript(() => {
    window.__cspViolations = [];
    document.addEventListener('securitypolicyviolation', (e) => {
      window.__cspViolations.push(`${e.violatedDirective} ← ${e.blockedURI || 'inline'}`);
    });
  });
  return { page, ctx, errors };
}

const shot = async (page, name) => {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${BROWSER}-${name}.png` });
};
const settle = (page, ms = 450) => page.waitForTimeout(ms);

const setCard = (page, prefix) => page.locator(`[data-set-card^="${prefix}"]`);
async function studySet(page, prefix, mode) {
  await setCard(page, prefix).getByRole('button', { name: new RegExp(mode, 'i') }).click();
}

// --- Akış yardımcıları ---
const feedIndex = (page) =>
  page.evaluate(() => {
    const el = document.querySelector('[role="feed"]');
    return el ? Math.round(el.scrollTop / el.clientHeight) : -1;
  });

async function activeCard(page) {
  const idx = await feedIndex(page);
  const card = page.locator('[data-feed-card]').nth(idx);
  const text = await card.innerText().catch(() => '');
  const kind = text.includes('CEVABI YAZ')
    ? 'ti'
    : (await card.locator('button').count()) >= 2
      ? 'mc'
      : text.includes('ANLAM') || text.includes('CEVAP')
        ? 'explainer'
        : 'unknown';
  const front = (await card.locator('h2').first().innerText().catch(() => '')).trim();
  return { idx, card, kind, front };
}

// ---------------------------------------------------------------------------

const server = await startPreview();
const browser = await launch();
console.log(`Motor: ${BROWSER} ${browser.version()}`);
console.log(`İçerik: ${TOTAL_MCQ} soru, ${TOTAL_CARDS} kart\n`);

try {
  const { page, errors } = await newPage(browser, { width: 440, height: 780 });
  await page.goto(URL);
  await page.getByRole('heading', { name: 'Derslerim' }).waitFor();

  // ===================== Ana ekran =====================
  const fontOk = await page.evaluate(async () => {
    await document.fonts.ready;
    return document.fonts.check('800 16px Nunito') && document.fonts.check('800 16px Nunito', 'ğşıİ');
  });
  check('Nunito pakete gömülü yükleniyor (Türkçe karakterler dahil)', fontOk);

  const courseBtn = page.getByRole('button', { name: /Mikrobiyoloji/ });
  const courseText = await courseBtn.innerText();
  check(
    'Mikrobiyoloji dersi hazır geliyor (2 set, tüm sorular ve kartlar)',
    courseText.includes(`2 set · ${TOTAL_MCQ} soru · ${TOTAL_CARDS} kart`),
    courseText.replace(/\n/g, ' ')
  );
  const homeText = await page.locator('body').innerText();
  check('XP / seri / günlük hedef yok', !/\bXP\b|Günlük Hedef|\d+\s*gün\b/.test(homeText));
  await shot(page, '01-dersler');

  // ===================== Ders sayfası =====================
  await courseBtn.click();
  await page.getByRole('heading', { name: 'Mikrobiyoloji' }).waitFor();
  check('"Tüm ders" kartı var', (await page.getByText('Tüm ders', { exact: true }).count()) > 0);
  check(
    'Hafta 7 ve Hafta 8 setleri var',
    (await setCard(page, 'Hafta 7').count()) === 1 && (await setCard(page, 'Hafta 8').count()) === 1
  );
  await shot(page, '02-ders');

  // ===================== Göz at =====================
  await studySet(page, 'Hafta 7', 'Göz at');
  await page.getByText(`${H7_MCQ} soru · ${H7_CARDS} kart`).waitFor();
  await page.getByRole('button', { name: new RegExp(`Sorular \\(${H7_MCQ}\\)`) }).click();
  check('Göz at: "Sorular" filtresi tüm soruları listeliyor', (await page.locator('ol > li').count()) === H7_MCQ);
  await page.getByPlaceholder(/Ara/).fill('Campylobacter');
  const searchHits = await page.locator('ol > li').count();
  check('Göz at: arama çalışıyor', searchHits > 0 && searchHits < H7_MCQ, `${searchHits} sonuç`);
  await page.getByPlaceholder(/Ara/).fill('');
  await page.locator('ol > li button').first().click();
  await page.locator('[data-browse-position]').waitFor();
  check('Göz at: tek öğe görünümü açılıyor', (await page.locator('[data-browse-position]').innerText()).startsWith('1 /'));
  check('Göz at: cevap başta gizli', (await page.locator('[data-browse-answer]').count()) === 0);
  await page.getByRole('button', { name: /Cevabı göster/ }).click();
  check('Göz at: "Cevabı göster" cevabı açıyor', (await page.locator('[data-browse-answer]').count()) === 1);
  await shot(page, '03-goz-at');
  await page.keyboard.press('ArrowRight');
  await settle(page, 300);
  check('Göz at: → sonraki öğeye geçiyor', (await page.locator('[data-browse-position]').innerText()).startsWith('2 /'));
  // Bir şıkka dokunmak da cevabı açar
  await page.locator('main button').first().click();
  check('Göz at: şıkka dokunmak cevabı açıyor', (await page.locator('[data-browse-answer]').count()) === 1);
  await page.keyboard.press('Escape');
  await page.locator('ol > li').first().waitFor();
  await page.getByRole('button', { name: 'Geri' }).click();
  await page.getByRole('heading', { name: 'Mikrobiyoloji' }).waitFor();

  // ===================== Soru çöz =====================
  await studySet(page, 'Hafta 8', 'Soru çöz');
  await page.getByText(`${H8_MCQ} sınav sorusu`, { exact: false }).waitFor();
  check('Soru çöz: başlangıçta soru sayısı seçiliyor', (await page.getByRole('button', { name: '10', exact: true }).count()) === 1);
  await page.getByRole('button', { name: '10', exact: true }).click();
  await page.getByRole('button', { name: 'Başla' }).click();

  const WRONG_FIRST = 3;
  let answered = 0;
  let explanationShown = 0;
  for (let i = 0; i < 10; i++) {
    await page.locator('[data-quiz-position]').waitFor();
    const stem = (await page.locator('main h2').first().innerText()).trim();
    const correct = ANSWER.get(stem);
    const opts = page.locator('[data-quiz-choices] button');
    const n = await opts.count();
    let clicked = false;
    for (let k = 0; k < n; k++) {
      const t = (await opts.nth(k).innerText()).replace(/^[A-F✓]\s*/, '').trim();
      const isCorrect = correct && t.endsWith(correct);
      if ((i < WRONG_FIRST && !isCorrect) || (i >= WRONG_FIRST && isCorrect)) {
        await opts.nth(k).click();
        clicked = true;
        break;
      }
    }
    if (!clicked) await opts.first().click();
    answered++;
    const cont = page.getByRole('button', { name: /Devam Et/i });
    await cont.waitFor();
    if ((await page.getByText(/Slayt \d+/).count()) > 0) explanationShown++;
    if (i === 0) await shot(page, '04-soru-geri-bildirim');
    await page.waitForTimeout(400); // yay animasyonu otursun (WebKit'te hareket hâlindeki düğme ıskalanabilir)
    await page.keyboard.press('Enter'); // masaüstü kısayolu
    await cont.waitFor({ state: 'detached', timeout: 5000 }).catch(() => {});
  }
  check('Soru çöz: her cevaptan sonra açıklama ve slayt kaynağı gösteriliyor', explanationShown === answered, `${explanationShown}/${answered}`);
  await page.locator('[data-quiz-score]').waitFor();
  const score = (await page.locator('[data-quiz-score]').innerText()).replace(/\s/g, '');
  check('Soru çöz: puan doğru hesaplanıyor', score === `${10 - WRONG_FIRST}/10`, score);
  check('Soru çöz: yanlışlar listeleniyor', (await page.getByText('YANLIŞ YAPTIKLARIN').count()) === 1);
  await shot(page, '05-soru-sonuc');
  await page.getByRole('button', { name: new RegExp(`Yanlışları tekrar çöz \\(${WRONG_FIRST}\\)`) }).click();
  await page.locator('[data-quiz-position]').waitFor();
  check('Soru çöz: "Yanlışları tekrar çöz" yalnız yanlışlarla başlıyor', (await page.locator('[data-quiz-position]').innerText()) === `1/${WRONG_FIRST}`);
  await page.getByRole('button', { name: 'Çıkış' }).click();
  await page.getByRole('heading', { name: 'Mikrobiyoloji' }).waitFor();

  // ===================== İlerleme kaydı =====================
  const h8Progress = await setCard(page, 'Hafta 8').locator('[data-progress-line]').innerText();
  check(
    'İlerleme: çözülen sorular set kartında görünüyor',
    h8Progress.includes(`10/${H8_ITEMS} çalışıldı`) &&
      h8Progress.includes(`${10 - WRONG_FIRST} doğru`) &&
      h8Progress.includes(`${WRONG_FIRST} yanlış`),
    h8Progress
  );
  await studySet(page, 'Hafta 8', 'Soru çöz');
  await page.locator('[data-pool-filter]').waitFor();
  check(
    'İlerleme: "Yanlışlarım" ve "Çözülmemiş" havuzları doğru sayıda',
    (await page.getByRole('button', { name: `Yanlışlarım (${WRONG_FIRST})` }).count()) === 1 &&
      (await page.getByRole('button', { name: `Çözülmemiş (${H8_MCQ - 10})` }).count()) === 1
  );
  await page.getByRole('button', { name: `Yanlışlarım (${WRONG_FIRST})` }).click();
  await page.getByRole('button', { name: 'Başla' }).click();
  await page.locator('[data-quiz-position]').waitFor();
  check('İlerleme: "Yanlışlarım" yalnız yanlış cevaplananları soruyor', (await page.locator('[data-quiz-position]').innerText()) === `1/${WRONG_FIRST}`);
  await page.getByRole('button', { name: 'Çıkış' }).click();
  await page.getByRole('heading', { name: 'Mikrobiyoloji' }).waitFor();

  // ===================== Kartlar =====================
  await studySet(page, 'Hafta 7', 'Kartlar');
  await page.locator('[data-card-front]').first().waitFor();
  const deckTab = page.getByRole('tab', { name: new RegExp(`Bilgi kartları \\(${H7_CARDS}\\)`) });
  check(
    'Kartlar: varsayılan deste bilgi kartları',
    (await deckTab.getAttribute('aria-selected')) === 'true' &&
      (await page.getByText(`${H7_CARDS} kart`, { exact: true }).count()) === 1
  );
  await page.getByRole('tab', { name: /Sorular/ }).click();
  check('Kartlar: "Sorular" destesine geçiliyor', (await page.getByText(`${H7_MCQ} kart`, { exact: true }).count()) === 1);
  await page.getByRole('tab', { name: /Bilgi kartları/ }).click();
  await page.locator('[data-card-front]').first().waitFor();
  const firstFront = (await page.locator('[data-card-front]').first().innerText()).trim();
  await page.locator('.preserve-3d').click();
  await settle(page, 800);
  check('Kartlar: kart çevrilince cevap görünüyor', await page.getByText('CEVAP').first().isVisible());
  await shot(page, '06-kart');
  await page.getByRole('button', { name: /Zor/i }).click();
  await settle(page);
  let reappeared = false;
  for (let i = 0; i < 8; i++) {
    const f = (await page.locator('[data-card-front]').first().innerText().catch(() => '')).trim();
    if (f === firstFront) {
      reappeared = true;
      break;
    }
    await page.getByRole('button', { name: /Kolay/i }).click();
    await settle(page, 400);
  }
  check('Kartlar: "Zor" işaretlenen kart aynı oturumda geri geliyor', reappeared);
  await page.getByRole('button', { name: 'Geri' }).click();
  await page.getByRole('heading', { name: 'Mikrobiyoloji' }).waitFor();

  // ===================== Akış (tüm ders) =====================
  await page.locator('[data-course-all]').getByRole('button', { name: /Akış/ }).click();
  await page.locator('[data-feed-card]').first().waitFor();
  await settle(page, 700);
  const first = await activeCard(page);
  check('Akış: anlatım kartıyla açılıyor', first.kind === 'explainer', first.front.slice(0, 40));
  check('Akış: XP/seri yerine doğru sayacı var', (await page.getByLabel(/doğru, \d+ cevap/).count()) === 1);
  await shot(page, '07-akis');

  const seen = { explainer: 0, mc: 0, ti: 0, unknown: 0 };
  let correctAnswers = 0;
  let waitedForExplanation = 0;
  for (let step = 0; step < 16; step++) {
    const c = await activeCard(page);
    seen[c.kind]++;
    if (c.kind === 'mc') {
      const answer = ANSWER.get(c.front);
      const opts = c.card.locator('button');
      const n = await opts.count();
      for (let k = 0; k < n; k++) {
        const t = (await opts.nth(k).innerText()).trim();
        if (answer && t.endsWith(answer)) {
          await opts.nth(k).click();
          correctAnswers++;
          break;
        }
      }
      await settle(page, 1300);
      if ((await feedIndex(page)) === c.idx) {
        // Açıklaması olan soru otomatik geçmez — okunması beklenir.
        if ((await c.card.getByText(/Devam etmek için yukarı kaydır/).count()) > 0) waitedForExplanation++;
        await page.keyboard.press('ArrowDown');
        await settle(page);
      }
      continue;
    }
    await page.keyboard.press('ArrowDown');
    await settle(page);
  }
  check('Akış: anlatım kartları var', seen.explainer > 0, `${seen.explainer}`);
  check('Akış: soru kartları var', seen.mc > 0, `${seen.mc}`);
  check('Akış: bilinmeyen kart türü yok', seen.unknown === 0);
  check('Akış: açıklamalı soru okunması için bekliyor', correctAnswers === 0 || waitedForExplanation > 0, `${waitedForExplanation}/${correctAnswers}`);
  await shot(page, '08-akis-soru');

  await settle(page, 900);
  const snapOffset = await page.evaluate(() => {
    const el = document.querySelector('[role="feed"]');
    const tops = [...el.querySelectorAll('[data-feed-card]')].map((s) => s.offsetTop);
    return Math.min(...tops.map((t) => Math.abs(el.scrollTop - t)));
  });
  check('Akış: kaydırma kart sınırına oturuyor', snapOffset < 2, `sapma ${snapOffset.toFixed(1)}px`);

  const wheelStart = await feedIndex(page);
  const box = await page.locator('[role="feed"]').boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + 60);
  await page.mouse.wheel(0, 120);
  await settle(page, 1200);
  check('Akış: tek tekerlek çentiği bir kart ilerletiyor', (await feedIndex(page)) === wheelStart + 1);

  // "Göster": Esc yalnızca pencereyi kapatır; sonra ok tuşları çalışır.
  let questionFound = false;
  for (let i = 0; i < 12 && !questionFound; i++) {
    const c = await activeCard(page);
    if (c.kind === 'mc' || c.kind === 'ti') {
      questionFound = true;
      break;
    }
    await page.keyboard.press('ArrowDown');
    await settle(page, 600);
  }
  if (questionFound) {
    await page.getByRole('button', { name: 'Cevabı göster' }).click();
    await page.getByRole('dialog').waitFor();
    await page.keyboard.press('Escape');
    await settle(page, 500);
    check(
      'Akış: "Göster" penceresinde Esc yalnızca pencereyi kapatıyor',
      (await page.getByRole('dialog').count()) === 0 && (await page.locator('[role="feed"]').count()) > 0
    );
    const afterDialog = await feedIndex(page);
    await page.keyboard.press('ArrowDown');
    await settle(page, 900);
    check('Akış: pencere kapandıktan sonra ok tuşları çalışıyor', (await feedIndex(page)) === afterDialog + 1);
  } else {
    check('Akış: "Göster" testi için soru kartı bulundu', false);
  }
  await page.keyboard.press('Escape');
  await page.getByRole('heading', { name: 'Mikrobiyoloji' }).waitFor();
  check('Akış: Esc derse geri döndürüyor', true);

  // ===================== Düzenleme kayıpsız mı =====================
  const h7Snapshot = () =>
    page.evaluate(() => {
      const s = JSON.parse(localStorage.getItem('kelime-ustasi.sets')).find((x) => x.name.startsWith('Hafta 7'));
      return JSON.stringify({ ids: s.questions.map((q) => q.id), updatedAt: s.updatedAt });
    });
  const beforeEdit = await h7Snapshot();
  await setCard(page, 'Hafta 7').getByRole('button', { name: 'Düzenle' }).click();
  const editText = await page.getByRole('dialog').locator('textarea').inputValue();
  check('Düzenle: şıklı sorular JSON olarak açılıyor', editText.includes('"type": "mcq"') && editText.includes('"explanation"'));
  await page.getByRole('dialog').getByRole('button', { name: 'Kaydet' }).click();
  await settle(page, 400);
  check(
    'Düzenle: değiştirmeden kaydetmek hiçbir şey kaybettirmiyor',
    (await setCard(page, 'Hafta 7').innerText()).includes(`${H7_MCQ} soru · ${H7_CARDS} kart`)
  );
  check(
    'Düzenle: değiştirmeden kaydetmek kimlikleri ve "düzenlenmemiş" durumunu koruyor',
    (await h7Snapshot()) === beforeEdit
  );

  // ===================== İçe aktarma =====================
  await page.getByRole('button', { name: /Bu derse set ekle/ }).click();
  await page.getByLabel('Set adı').first().fill('Deneme seti');
  await page.locator('textarea').fill(['Ephemeral - Kısa süreli', 'Ubiquitous - Her yerde bulunan', 'BOZUKSATIR'].join('\n'));
  await page.getByRole('button', { name: 'Kaydet', exact: true }).click();
  await page.getByText(/kaydedildi/).waitFor();
  check('İçe aktar: bozuk satır uyarı olarak gösteriliyor', (await page.getByText(/BOZUKSATIR/).count()) > 0);
  check('İçe aktar: set derse eklendi', (await setCard(page, 'Deneme seti').count()) === 1);
  await page.locator('textarea').fill('asdf qwer zxcv');
  await page.getByRole('button', { name: 'Kaydet', exact: true }).click();
  check('İçe aktar: geçersiz girdi Türkçe hata veriyor', (await page.getByText(/Geçerli "Kelime - Tanım" satırı bulunamadı/).count()) > 0);
  await setCard(page, 'Deneme seti').getByRole('button', { name: 'Sil' }).click();
  await page.getByRole('button', { name: 'Evet, sil' }).click();
  await settle(page, 300);
  await page.getByRole('button', { name: 'Derslere dön' }).click();
  await page.getByRole('heading', { name: 'Derslerim' }).waitFor();

  // Ders paketi JSON'u ana ekrandan
  await page.getByRole('button', { name: /İçe aktar/ }).click();
  const pack = {
    course: 'Test Dersi',
    sets: [
      {
        name: 'Ünite 1',
        items: [
          { type: 'mcq', question: 'İki artı iki?', options: ['3', '4', '5'], answer: '4', explanation: 'Toplama.' },
          { type: 'card', front: 'H2O', back: 'Su' },
        ],
      },
    ],
  };
  await page.locator('textarea').fill(JSON.stringify(pack));
  await page.getByRole('button', { name: 'Kaydet', exact: true }).click();
  await page.getByText(/"Test Dersi" dersine 1 set eklendi/).waitFor();
  check('İçe aktar: ders paketi JSON\'u ders olarak ekleniyor', (await page.getByRole('button', { name: /Test Dersi/ }).count()) === 1);

  // ===================== Kalıcılık =====================
  await page.reload();
  await page.getByRole('heading', { name: 'Derslerim' }).waitFor();
  check('Yenileme sonrası dersler korunuyor', (await page.getByRole('button', { name: /Test Dersi/ }).count()) === 1);
  check(
    'Yenileme sonrası ilerleme korunuyor',
    (await page.evaluate(() => Object.keys(JSON.parse(localStorage.getItem('kelime-ustasi.progress.v1') ?? '{}')).length)) >= 10
  );
  check(
    'Hazır ders yenilemede çoğaltılmıyor',
    (await page.getByRole('button', { name: /Mikrobiyoloji/ }).count()) === 1 &&
      (await page.getByRole('button', { name: /Mikrobiyoloji/ }).innerText()).includes('2 set')
  );

  // ===================== Konu anlatımı (Topografik Anatomi) =====================
  await page.getByRole('button', { name: /Topografik Anatomi/ }).click();
  await page.getByRole('heading', { name: 'Topografik Anatomi' }).waitFor();
  check(
    'Topografik Anatomi: 5 set hazır geliyor',
    (await Promise.all(['Damarlar', 'Lenf', 'Sinirler', 'Gövde', 'Klinik'].map((p) => setCard(page, p).count()))).every((n) => n === 1)
  );
  await studySet(page, 'Damarlar', 'Konu anlatımı');
  await page.getByText('İçindekiler').first().waitFor();
  check(
    'Konu anlatımı: tüm bölümler gösteriliyor',
    (await page.locator('[data-lesson-section]').count()) === TOPO_DAMAR.lesson.length,
    `${await page.locator('[data-lesson-section]').count()} bölüm`
  );
  check('Konu anlatımı: tablo biçimleniyor', (await page.locator('[data-lesson-section] table').count()) > 0);
  check('Konu anlatımı: “Sınavda” kutuları var', (await page.locator('[data-exam-tip]').count()) > 0);
  check('Konu anlatımı: **kalın** vurgular biçimleniyor', (await page.locator('[data-lesson-section] strong').count()) > 10);
  const target = TOPO_DAMAR.lesson.findIndex((x) => x.title.startsWith('Vena cava'));
  await page.getByRole('navigation', { name: 'İçindekiler' }).getByRole('button', { name: /Vena cava/ }).click();
  await settle(page, 1000);
  const jumpTop = await page.locator('[data-lesson-section]').nth(target).evaluate((el) => el.getBoundingClientRect().top);
  check('Konu anlatımı: içindekiler bölüme götürüyor', Math.abs(jumpTop) < 60, `${Math.round(jumpTop)}px`);
  await shot(page, '10-konu-anlatimi');
  await settle(page, 900); // kaydırma bitince kalınan bölüm kaydedilir
  await page.getByRole('button', { name: /Soru çöz/ }).last().click();
  await page.getByText(`${count(TOPO_DAMAR, 'mcq')} sınav sorusu`, { exact: false }).waitFor();
  check('Konu anlatımı: sonundan aynı setin sorularına geçiliyor', true);
  await page.getByRole('button', { name: 'Geri' }).first().click();
  await page.getByRole('heading', { name: 'Topografik Anatomi' }).waitFor();
  await page.locator('[data-course-all]').getByRole('button', { name: /Konu anlatımı/ }).click();
  await page.getByText('İçindekiler').first().waitFor();
  check(
    'Konu anlatımı: tüm ders açılınca her setin anlatımı kendi başlığıyla',
    (await page.locator('[data-lesson-group]').count()) === TOPO_SETS.length &&
      (await page.locator('[data-lesson-section]').count()) === TOPO_SETS.reduce((n, x) => n + x.lesson.length, 0)
  );
  await page.keyboard.press('Escape');
  await page.getByRole('heading', { name: 'Topografik Anatomi' }).waitFor();
  check('Konu anlatımı: Esc derse döndürüyor', true);
  // Kaldığın yerden devam: Damarlar anlatımı yeniden açılınca son okunan bölüm önerilir.
  await studySet(page, 'Damarlar', 'Konu anlatımı');
  await page.getByText('İçindekiler').first().waitFor();
  const resume = page.locator('[data-lesson-resume]');
  check(
    'Konu anlatımı: yeniden açınca "Kaldığın yerden devam et" son bölümü gösteriyor',
    (await resume.count()) === 1 && (await resume.innerText()).includes(TOPO_DAMAR.lesson[target].title)
  );
  await resume.click();
  await settle(page, 1000);
  const resumeTop = await page.locator('[data-lesson-section]').nth(target).evaluate((el) => el.getBoundingClientRect().top);
  check('Konu anlatımı: devam düğmesi o bölüme götürüyor', Math.abs(resumeTop) < 60, `${Math.round(resumeTop)}px`);
  await page.keyboard.press('Escape');
  await page.getByRole('heading', { name: 'Topografik Anatomi' }).waitFor();

  await page.getByRole('button', { name: 'Derslere dön' }).click();
  await page.getByRole('button', { name: /Mikrobiyoloji/ }).click();
  await page.getByRole('heading', { name: 'Mikrobiyoloji' }).waitFor();
  check(
    'Mikrobiyoloji: 8. haftada tablolar anlatımı var, 7. haftada yok',
    (await setCard(page, 'Hafta 8').getByRole('button', { name: /Konu anlatımı/ }).count()) === 1 &&
      (await setCard(page, 'Hafta 7').getByRole('button', { name: /Konu anlatımı/ }).count()) === 0
  );
  await studySet(page, 'Hafta 8', 'Konu anlatımı');
  await page.getByText('İçindekiler').first().waitFor();
  check(
    'Mikrobiyoloji: 8. hafta anlatımında tüm tablolar',
    (await page.locator('[data-lesson-section]').count()) === H8.lesson.length &&
      (await page.locator('[data-lesson-section] table').count()) >= 10
  );
  await page.keyboard.press('Escape');
  await page.getByRole('heading', { name: 'Mikrobiyoloji' }).waitFor();
  await page.getByRole('button', { name: 'Derslere dön' }).click();
  await page.getByRole('heading', { name: 'Derslerim' }).waitFor();

  const csp1 = await page.evaluate(() => window.__cspViolations);
  check('CSP ihlali yok', csp1.length === 0, csp1.slice(0, 3).join(' | '));
  check('Konsol hatası yok', errors.length === 0, errors.slice(0, 3).join(' | '));

  // ===================== Geniş masaüstü penceresi =====================
  const wide = await newPage(browser, { width: 1280, height: 800 });
  const storage = await page.evaluate(() => JSON.stringify(localStorage));
  await wide.page.goto(URL);
  await wide.page.evaluate((s) => {
    localStorage.clear();
    for (const [k, v] of Object.entries(JSON.parse(s))) localStorage.setItem(k, v);
  }, storage);
  await wide.page.reload();
  await wide.page.getByRole('button', { name: /Mikrobiyoloji/ }).click();
  await studySet(wide.page, 'Hafta 8', 'Akış');
  await wide.page.locator('[data-feed-card]').first().waitFor();
  await settle(wide.page, 700);
  const layout = await wide.page.evaluate(() => {
    const col = document.querySelector('[data-feed-card] > div').getBoundingClientRect();
    const rail = document.querySelector('[aria-label="Cevabı göster"]').getBoundingClientRect();
    return { colW: col.width, colL: col.left, colR: col.right, railR: rail.right };
  });
  check('Geniş pencere: akış ortalanmış dar sütunda', layout.colW <= 448 && layout.colL > 300, `genişlik ${layout.colW}`);
  check('Geniş pencere: ray sütunun içinde', layout.railR <= layout.colR + 1);
  const gutterStart = await feedIndex(wide.page);
  await wide.page.mouse.move(120, 400);
  await wide.page.mouse.wheel(0, 120);
  await settle(wide.page, 1200);
  check('Geniş pencere: yan boşlukta tekerlek akışı kaydırıyor', (await feedIndex(wide.page)) === gutterStart + 1);
  await shot(wide.page, '09-genis-pencere');
  check('Geniş pencere: konsol hatası yok', wide.errors.length === 0, wide.errors.slice(0, 3).join(' | '));

  // ===================== Hazır içerik güncellemesi =====================
  // Sürümlemeden önceki bir kurulumun depolamasını taklit et: tek paket işareti, `bundle`
  // alanı olmayan setler, rastgele soru kimlikleri. Hafta 7'ye dokunulmamış (eski içerik),
  // Hafta 8 kullanıcı tarafından düzenlenmiş.
  const up = await newPage(browser, { width: 440, height: 780 });
  await up.page.goto(URL);
  await up.page.getByRole('heading', { name: 'Derslerim' }).waitFor();
  await up.page.evaluate(() => {
    const sets = JSON.parse(localStorage.getItem('kelime-ustasi.sets'));
    for (const s of sets.filter((x) => x.name.startsWith('Hafta '))) {
      delete s.bundle;
      s.questions = s.questions.map((q, i) => ({ ...q, id: `eski-${s.name}-${i}` }));
      if (s.name.startsWith('Hafta 7')) {
        s.questions[0] = { ...s.questions[0], front: 'ESKİ SÜRÜM SORUSU' };
      } else {
        s.questions[0] = { ...s.questions[0], front: 'BENİM DÜZENLEMEM' };
        s.updatedAt = new Date(Date.parse(s.createdAt) + 60_000).toISOString();
      }
    }
    localStorage.setItem('kelime-ustasi.sets', JSON.stringify(sets));
    const keep = JSON.parse(localStorage.getItem('kelime-ustasi.seededPacks') ?? '[]').filter((e) => !e.startsWith('mikrobiyoloji'));
    localStorage.setItem('kelime-ustasi.seededPacks', JSON.stringify([...keep, 'mikrobiyoloji-hafta-7-8']));
  });
  await up.page.reload();
  await up.page.getByRole('heading', { name: 'Derslerim' }).waitFor();
  const upgraded = await up.page.evaluate(() => {
    const sets = JSON.parse(localStorage.getItem('kelime-ustasi.sets'));
    const h7 = sets.find((s) => s.name.startsWith('Hafta 7'));
    const h8 = sets.find((s) => s.name.startsWith('Hafta 8'));
    return {
      count: sets.filter((s) => s.name.startsWith('Hafta ')).length,
      h7Old: h7.questions.some((q) => q.front === 'ESKİ SÜRÜM SORUSU'),
      h7Len: h7.questions.length,
      h7Id: h7.questions[0].id,
      h7Bundle: h7.bundle,
      h8Kept: h8.questions[0].front === 'BENİM DÜZENLEMEM',
      seeded: JSON.parse(localStorage.getItem('kelime-ustasi.seededPacks')),
    };
  });
  check(
    'Güncelleme: dokunulmamış hazır set yeni sürümle yenileniyor',
    !upgraded.h7Old && upgraded.h7Len === H7_MCQ + H7_CARDS && upgraded.h7Bundle?.key === 'mikrobiyoloji-hafta-7',
    `${upgraded.h7Len} öğe`
  );
  check('Güncelleme: soru kimlikleri sabit (tekrar ilerlemesi korunur)', upgraded.h7Id === 'mikrobiyoloji-hafta-7:q01', upgraded.h7Id);
  check('Güncelleme: kullanıcının düzenlediği set korunuyor', upgraded.h8Kept);
  check('Güncelleme: set çoğaltılmıyor', upgraded.count === 2, `${upgraded.count} set`);
  await up.page.reload();
  await up.page.getByRole('heading', { name: 'Derslerim' }).waitFor();
  check(
    'Güncelleme: ikinci açılışta tekrar uygulanmıyor',
    await up.page.evaluate(
      () => JSON.parse(localStorage.getItem('kelime-ustasi.sets')).find((s) => s.name.startsWith('Hafta 8')).questions[0].front === 'BENİM DÜZENLEMEM'
    ),
    upgraded.seeded.join(', ')
  );
  check('Güncelleme: konsol hatası yok', up.errors.length === 0, up.errors.slice(0, 3).join(' | '));

  // ===================== Açılışta uzaktan içerik güncellemesi =====================
  // GitHub'da daha yeni bir sürüm varmış gibi: manifest'te Hafta 7'nin sürümü yükselmiş ve
  // ilk sorusu değişmiş. Açılışta indirilip uygulanmalı; ilerleme ve soru kimliği korunmalı.
  const ota = await newPage(browser, { width: 440, height: 780 });
  await ota.page.goto(URL);
  await ota.page.getByRole('heading', { name: 'Derslerim' }).waitFor();
  check('Sürüm: ana sayfada uygulama sürümü yazıyor', (await ota.page.locator('[data-app-version]').innerText()).includes(PKG_VERSION));
  await ota.page.evaluate(() => {
    const at = new Date().toISOString();
    localStorage.setItem(
      'kelime-ustasi.progress.v1',
      JSON.stringify({ 'mikrobiyoloji-hafta-7:q01': { seen: 1, correct: 1, wrong: 0, last: 'correct', at } })
    );
  });
  const fakeManifest = structuredClone(MANIFEST);
  for (const p of fakeManifest.packs) for (const x of p.sets) if (x.key === 'mikrobiyoloji-hafta-7') x.version = 99;
  const fakeH7 = structuredClone(H7);
  fakeH7.items[0] = { ...fakeH7.items[0], question: 'GÜNCEL SORU (uzaktan)' };
  await ota.page.route('https://api.github.com/repos/erebb/erebb/releases/latest', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: CORS,
      body: JSON.stringify({ tag_name: 'v9.9.9', html_url: 'https://github.com/erebb/erebb/releases/tag/v9.9.9' }),
    })
  );
  await ota.page.route('https://raw.githubusercontent.com/erebb/erebb/v9.9.9/content/**', (r) => {
    const file = r.request().url().split('/').pop();
    const body = file === 'manifest.json' ? fakeManifest : file === 'mikrobiyoloji-hafta-7.json' ? fakeH7 : null;
    return body
      ? r.fulfill({ status: 200, contentType: 'application/json', headers: CORS, body: JSON.stringify(body) })
      : r.fulfill({ status: 200, contentType: 'application/json', headers: CORS, body: '{}' });
  });
  await ota.page.reload();
  await ota.page.locator('[data-update-toast="content"]').waitFor({ timeout: 10000 });
  check('Güncelleme (uzak): "Yeni içerik yüklendi" bildirimi', (await ota.page.locator('[data-update-toast="content"]').innerText()).includes('Hafta 7'));
  const otaState = await ota.page.evaluate(() => {
    const sets = JSON.parse(localStorage.getItem('kelime-ustasi.sets'));
    const h7 = sets.find((s) => s.name.startsWith('Hafta 7'));
    return {
      first: h7.questions[0].front,
      id: h7.questions[0].id,
      version: h7.bundle?.version,
      kept: Boolean(JSON.parse(localStorage.getItem('kelime-ustasi.progress.v1'))['mikrobiyoloji-hafta-7:q01']),
      seeded: JSON.parse(localStorage.getItem('kelime-ustasi.seededPacks')),
    };
  });
  check(
    'Güncelleme (uzak): yeni sürüm indirilip uygulanıyor',
    otaState.first === 'GÜNCEL SORU (uzaktan)' && otaState.version === 99 && otaState.seeded.includes('mikrobiyoloji-hafta-7@99'),
    `${otaState.first} · v${otaState.version}`
  );
  check('Güncelleme (uzak): ilerleme ve soru kimliği korunuyor', otaState.kept && otaState.id === 'mikrobiyoloji-hafta-7:q01');
  await ota.page.getByRole('button', { name: /Mikrobiyoloji/ }).click();
  await studySet(ota.page, 'Hafta 7', 'Göz at');
  await ota.page.getByPlaceholder(/Ara/).fill('GÜNCEL SORU');
  check(
    'Güncelleme (uzak): açık uygulama yeni içeriği sayfa yenilenmeden gösteriyor',
    (await ota.page.locator('ol > li').count()) === 1
  );
  const csp3 = await ota.page.evaluate(() => window.__cspViolations);
  check('Güncelleme (uzak): CSP GitHub isteklerine izin veriyor', csp3.length === 0, csp3.slice(0, 3).join(' | '));
  check('Güncelleme (uzak): konsol hatası yok', ota.errors.length === 0, ota.errors.slice(0, 3).join(' | '));

  // ===================== Silinen hazır ders geri gelmez =====================
  await page.getByRole('button', { name: /Mikrobiyoloji/ }).click();
  await page.getByRole('button', { name: 'Dersi sil' }).click();
  await page.getByRole('button', { name: 'Evet, sil' }).click();
  await page.getByRole('heading', { name: 'Derslerim' }).waitFor();
  await page.reload();
  await page.getByRole('heading', { name: 'Derslerim' }).waitFor();
  check('Silinen hazır ders yeniden açılışta geri gelmiyor', (await page.getByRole('button', { name: /Mikrobiyoloji/ }).count()) === 0);
} finally {
  await browser.close();
  stopPreview(server);
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} kontrol geçti (${BROWSER}).`);
if (failed.length) {
  console.log('Başarısız:', failed.map((f) => f.name).join('; '));
  process.exit(1);
}
process.exit(0);
