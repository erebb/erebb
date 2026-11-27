// Kelime Ustası — uçtan uca duman testi.
//
// Üretim derlemesini (dist/) `vite preview` ile sunar ve uygulamanın ana akışlarını
// gerçek bir tarayıcı motorunda sürer. CI'da macOS üzerinde WebKit ile koşar —
// masaüstü uygulamasının kullandığı WKWebView ile aynı motor.
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

const CSP = JSON.parse(readFileSync(new globalThis.URL('../src-tauri/tauri.conf.json', import.meta.url)))
  .app.security.csp;

// Bilinen cevaplar — testin doğru/yanlış cevaplamayı seçebilmesi için.
const WORDS = {
  Ephemeral: 'Kısa süreli, geçici',
  Ubiquitous: 'Her yerde bulunan',
  'Well-being': 'Sağlıklı olma hâli',
  Serendipity: 'Şans eseri güzel keşif',
  Meticulous: 'Titiz, çok dikkatli',
  Resilient: 'Dayanıklı, çabuk toparlanan',
};

// ---------------------------------------------------------------------------

const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
}

async function startPreview() {
  const proc = spawn('npx', ['vite', 'preview', '--port', String(PORT), '--strictPort'], {
    stdio: ['ignore', 'pipe', 'pipe'],
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
  proc.kill();
  throw new Error(`vite preview başlamadı:\n${log}`);
}

async function launch() {
  const engines = { chromium, webkit, firefox };
  const engine = engines[BROWSER];
  if (!engine) throw new Error(`Bilinmeyen E2E_BROWSER: ${BROWSER}`);
  const opts = BROWSER === 'chromium' && process.env.PW_CHROMIUM_PATH
    ? { executablePath: process.env.PW_CHROMIUM_PATH }
    : {};
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

// --- Akış yardımcıları ---
const feedIndex = (page) =>
  page.evaluate(() => {
    const el = document.querySelector('[role="feed"]');
    return el ? Math.round(el.scrollTop / el.clientHeight) : -1;
  });

async function settle(page, ms = 450) {
  await page.waitForTimeout(ms);
}

async function activeCard(page) {
  const idx = await feedIndex(page);
  const card = page.locator('[data-feed-card]').nth(idx);
  const text = await card.innerText().catch(() => '');
  const kind = text.includes('BU NE DEMEK?')
    ? 'mc'
    : text.includes('ANLAMINI YAZ')
      ? 'ti'
      : text.includes('ANLAM')
        ? 'explainer'
        : 'unknown';
  const word = await card.locator('h2').first().innerText().catch(() => '');
  return { idx, card, kind, word: word.trim() };
}

async function importPaste(page, name, lines) {
  await page.getByRole('tab', { name: /Metin Yapıştır/i }).click();
  await page.fill('input[placeholder*="Set adı"]', name);
  await page.fill('textarea', lines.join('\n'));
  await page.getByRole('button', { name: /Seti Kaydet/i }).click();
}

async function openSetMode(page, setName, label) {
  const card = page.locator('div.rounded-2xl', { hasText: setName }).filter({
    has: page.getByRole('button', { name: new RegExp(label, 'i') }),
  });
  await card.last().getByRole('button', { name: new RegExp(label, 'i') }).click();
}

// ---------------------------------------------------------------------------

const server = await startPreview();
const browser = await launch();
console.log(`Motor: ${BROWSER} ${browser.version()}\n`);

try {
  // ===================== Mobil boyutlu pencere =====================
  const { page, errors } = await newPage(browser, { width: 390, height: 844 });
  await page.goto(URL);
  await page.getByText('Kelime Ustası').first().waitFor();

  const fontOk = await page.evaluate(async () => {
    await document.fonts.ready;
    return document.fonts.check('800 16px Nunito') && document.fonts.check('800 16px Nunito', 'ğşıİ');
  });
  check('Nunito pakete gömülü yükleniyor (Türkçe karakterler dahil)', fontOk);

  // --- İçe aktarma ---
  await importPaste(page, 'Test Seti', [
    ...Object.entries(WORDS).map(([w, m]) => `${w} - ${m}`),
    'BOZUKSATIR',
  ]);
  await page.getByText(/kaydedildi/).waitFor();
  check('Bozuk satır hata değil uyarı olarak gösteriliyor', (await page.getByText(/BOZUKSATIR/).count()) > 0);
  check(
    '6 çift ayrıştırıldı (tireli "Well-being" bozulmadı)',
    (await page.getByText(/kaydedildi — 6 soru/).count()) > 0
  );

  await page.fill('textarea', 'asdf qwer zxcv');
  await page.getByRole('button', { name: /Seti Kaydet/i }).click();
  check(
    'Geçersiz girdi Türkçe hata gösteriyor',
    (await page.getByText(/Geçerli "Kelime - Tanım" satırı bulunamadı/).count()) > 0
  );
  await shot(page, '01-pano');

  // --- Akış ---
  await openSetMode(page, 'Test Seti', 'Akış');
  await page.locator('[data-feed-card]').first().waitFor();
  await settle(page, 700);
  await shot(page, '02-akis-anlatim');

  const first = await activeCard(page);
  check('Akış anlatım kartıyla açılıyor', first.kind === 'explainer', first.word);
  check('İlk kartta "Yukarı kaydır" ipucu var', await page.getByText('Yukarı kaydır').first().isVisible());
  const initialCount = await page.locator('[data-feed-card]').count();

  const feed = page.locator('[role="feed"]');
  await feed.focus();

  const seen = { explainer: 0, mc: 0, ti: 0, unknown: 0 };
  let autoAdvanceOk = 0;
  let autoAdvanceFail = 0;
  let wrongStayed = null;
  let deliberatelyWrongDone = false;

  for (let step = 0; step < 28; step++) {
    const c = await activeCard(page);
    seen[c.kind]++;
    const answer = WORDS[c.word];

    if (c.kind === 'mc' && answer) {
      const options = c.card.locator('button');
      const n = await options.count();
      let target = -1;
      for (let k = 0; k < n; k++) {
        const t = (await options.nth(k).innerText()).trim();
        const isCorrect = t.endsWith(answer);
        if (!deliberatelyWrongDone ? !isCorrect : isCorrect) {
          target = k;
          break;
        }
      }
      if (target === -1) target = 0;
      const willBeWrong = !deliberatelyWrongDone;
      await options.nth(target).click();
      if (willBeWrong) {
        deliberatelyWrongDone = true;
        await settle(page, 1500);
        const stayed = (await feedIndex(page)) === c.idx;
        const revealed = (await c.card.getByText(/Doğru cevap:/).count()) > 0;
        wrongStayed = stayed && revealed;
        await feed.press('ArrowDown');
        await settle(page);
      } else {
        await settle(page, 1600);
        if ((await feedIndex(page)) === c.idx + 1) autoAdvanceOk++;
        else autoAdvanceFail++;
      }
      continue;
    }

    if (c.kind === 'ti' && answer) {
      await c.card.locator('input').fill(answer.toLocaleUpperCase('tr') + '  '); // büyük harf + boşluk: normalize edilmeli
      await c.card.getByRole('button', { name: /Kontrol Et/i }).click();
      await settle(page, 1600);
      if ((await feedIndex(page)) === c.idx + 1) autoAdvanceOk++;
      else autoAdvanceFail++;
      await feed.focus();
      continue;
    }

    await feed.press('ArrowDown');
    await settle(page);
  }

  check('Anlatım kartları akışta', seen.explainer > 0, `${seen.explainer}`);
  check('Çoktan seçmeli kartlar akışta', seen.mc > 0, `${seen.mc}`);
  check('Yazılı kartlar akışta', seen.ti > 0, `${seen.ti}`);
  check('Bilinmeyen kart türü yok', seen.unknown === 0, `${seen.unknown}`);
  check('Yanlış cevap ekranda kalıp doğru cevabı gösteriyor', wrongStayed === true);
  check(
    'Doğru cevapta otomatik ilerliyor (yazılıda büyük harf/boşluk tolere ediliyor)',
    autoAdvanceOk > 0 && autoAdvanceFail === 0,
    `${autoAdvanceOk} ilerledi, ${autoAdvanceFail} takıldı`
  );
  const grown = await page.locator('[data-feed-card]').count();
  check('Akış sonsuz: yeni kartlar üretildi', grown > initialCount, `${initialCount} → ${grown}`);

  await settle(page, 900);
  const snapOffset = await page.evaluate(() => {
    const el = document.querySelector('[role="feed"]');
    const tops = [...el.querySelectorAll('[data-feed-card]')].map((s) => s.offsetTop);
    return Math.min(...tops.map((t) => Math.abs(el.scrollTop - t)));
  });
  check('Kaydırma kart sınırına oturuyor', snapOffset < 2, `sapma ${snapOffset.toFixed(1)}px`);

  const kbStart = await feedIndex(page);
  await feed.press('ArrowDown');
  await feed.press('ArrowDown');
  await feed.press('ArrowDown');
  await settle(page, 1400);
  const kbEnd = await feedIndex(page);
  check('Hızlı art arda 3 ok tuşu 3 kart ilerletiyor', kbEnd === kbStart + 3, `${kbStart} → ${kbEnd}`);

  const before = await feedIndex(page);
  await feed.press('ArrowUp');
  await settle(page, 700);
  check('Yukarı ok önceki karta dönüyor', (await feedIndex(page)) === before - 1);
  await shot(page, '03-akis-soru');

  // Escape ile çık (masaüstü kısayolu) → XP ve seri işlenmiş olmalı
  await feed.press('Escape');
  await page.getByText('Soru Setlerim').waitFor();
  const header = await page.locator('header').first().innerText();
  const xp = Number((header.match(/(\d+)\s*XP/) ?? [0, 0])[1]);
  check('Esc akıştan çıkıyor ve XP işleniyor', xp > 0, `${xp} XP`);
  check('Seri 1 gün oldu', /\b1\s*gün/.test(header));

  await page.reload();
  await page.getByText('Soru Setlerim').waitFor();
  const headerAfter = await page.locator('header').first().innerText();
  check(
    'XP ve seri sayfa yenilemesinden sonra korunuyor (LocalStorage)',
    Number((headerAfter.match(/(\d+)\s*XP/) ?? [0, 0])[1]) === xp
  );

  await openSetMode(page, 'Test Seti', 'Akış');
  await settle(page, 700);
  check('Kaydırma ipucu ikinci açılışta çıkmıyor', !(await page.getByText('Yukarı kaydır').first().isVisible().catch(() => false)));

  // Tek fare tekerleği çentiği bir sonraki karta geçirmeli
  const wheelStart = await feedIndex(page);
  const box = await page.locator('[role="feed"]').boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, 120);
  await settle(page, 1200);
  const wheelEnd = await feedIndex(page);
  check('Tek tekerlek çentiği bir kart ilerletiyor', wheelEnd === wheelStart + 1, `${wheelStart} → ${wheelEnd}`);

  // Bir "trackpad kaydırması": art arda gelen, azalan küçük olaylar (atalet kuyruğu) tek kart.
  const swipeStart = await feedIndex(page);
  for (const d of [6, 14, 28, 40, 34, 26, 18, 12, 8, 5, 3, 2, 1]) {
    await page.mouse.wheel(0, d);
    await page.waitForTimeout(16);
  }
  await settle(page, 1200);
  const swipeEnd = await feedIndex(page);
  check('Tek trackpad kaydırması (atalet dahil) tam bir kart ilerletiyor', swipeEnd === swipeStart + 1, `${swipeStart} → ${swipeEnd}`);

  // Ayrı çentikler (araları > sessizlik süresi) ayrı adımlardır; ters yön geri götürür.
  await page.mouse.wheel(0, -120);
  await page.waitForTimeout(400);
  await page.mouse.wheel(0, -120);
  await settle(page, 1200);
  check('İki ayrı geri çentik iki kart geri götürüyor', (await feedIndex(page)) === swipeEnd - 2);

  // "Kelimeyi göster": bir soru kartına gel, pencereyi aç; Esc yalnızca pencereyi kapatmalı,
  // akıştan çıkmamalı; sonra ok tuşları çalışmaya devam etmeli (odak body'ye düşse bile).
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
    await page.getByRole('button', { name: 'Kelimeyi göster' }).click();
    await page.getByRole('dialog').waitFor();
    await page.keyboard.press('Escape');
    await settle(page, 500);
    const dialogClosed = (await page.getByRole('dialog').count()) === 0;
    const stillInFeed = (await page.locator('[role="feed"]').count()) > 0;
    check('"Göster" penceresinde Esc yalnızca pencereyi kapatıyor', dialogClosed && stillInFeed);
    const afterDialog = await feedIndex(page);
    await page.keyboard.press('ArrowDown');
    await settle(page, 900);
    check('Pencere kapandıktan sonra ok tuşları çalışıyor', (await feedIndex(page)) === afterDialog + 1);
  } else {
    check('"Göster" testi için soru kartı bulundu', false);
  }

  await page.getByRole('button', { name: /Akıştan çık/i }).click();
  await page.getByText('Soru Setlerim').waitFor();

  // --- Kartlar ---
  await openSetMode(page, 'Test Seti', 'Kartlar');
  await page.getByText('SORU').first().waitFor();
  const firstWord = (await page.locator('.preserve-3d p').first().innerText()).trim();
  await page.locator('.preserve-3d').click();
  await settle(page, 800);
  check('Kart çevrilince cevap görünüyor', await page.getByText('CEVAP').first().isVisible());
  await shot(page, '04-kart');
  await page.getByRole('button', { name: /Zor/i }).click();
  await settle(page);
  let reappeared = false;
  for (let i = 0; i < 8; i++) {
    if ((await page.getByText('Oturum tamamlandı').count()) > 0) break;
    const w = (await page.locator('.preserve-3d p').first().innerText().catch(() => '')).trim();
    if (w === firstWord) {
      reappeared = true;
      break;
    }
    await page.getByRole('button', { name: /Kolay/i }).click();
    await settle(page, 400);
  }
  check('"Zor" işaretlenen kart aynı oturumda geri geliyor', reappeared, firstWord);
  await page.getByRole('button', { name: 'Geri' }).click();
  await page.getByText('Soru Setlerim').waitFor();

  // --- Test (can sistemi) ---
  await importPaste(page, 'Quiz Seti', Array.from({ length: 12 }, (_, i) => `Soru${i} - Cevap${i}`));
  await page.getByText(/kaydedildi — 12 soru/).waitFor();
  await openSetMode(page, 'Quiz Seti', 'Test');
  let gameOver = false;
  for (let i = 0; i < 40 && !gameOver; i++) {
    if ((await page.getByText('Canların bitti').count()) > 0) {
      gameOver = true;
      break;
    }
    // Geri bildirim şeridi açıksa önce onu geç. Şerit yay animasyonuyla içeri kayar;
    // WebKit'te hareket hâlindeki düğmeye yapılan tıklama ıskalanabildiği için oturmasını
    // bekle, tıkla ve kaybolduğunu doğrula — yoksa döngü kilitli kutuya yazmaya çalışır.
    const cont = page.getByRole('button', { name: /Devam Et/i });
    if (await cont.isVisible().catch(() => false)) {
      await page.waitForTimeout(450);
      await cont.click();
      await cont.waitFor({ state: 'detached', timeout: 5000 }).catch(() => {});
      continue;
    }
    const prompt = (await page.locator('main h2').first().innerText().catch(() => '')).trim();
    const want = prompt.replace('Soru', 'Cevap');
    if ((await page.locator('main input').count()) > 0) {
      await page.locator('main input').fill('kesinlikle-yanlis');
      await page.getByRole('button', { name: /Kontrol Et/i }).click();
    } else if ((await page.getByText('Çiftleri eşleştir').count()) > 0) {
      const cols = page.locator('main .grid.grid-cols-2 > div');
      const left = cols.nth(0).locator('button');
      const right = cols.nth(1).locator('button');
      const leftWord = (await left.nth(0).innerText()).trim().replace('Soru', 'Cevap');
      for (let k = 0; k < (await right.count()); k++) {
        if ((await right.nth(k).innerText()).trim() !== leftWord) {
          await left.nth(0).click();
          await right.nth(k).click();
          break;
        }
      }
    } else {
      const opts = page.locator('main button');
      for (let k = 0; k < (await opts.count()); k++) {
        if (!(await opts.nth(k).innerText()).includes(want)) {
          await opts.nth(k).click();
          break;
        }
      }
    }
    // Cevabın sonucunu bekle: geri bildirim şeridi ya da Oyun Bitti. (Eşleştirmede yanlış çift
    // şerit açmaz; o durumda kısa beklemeden sonra döngü yeni bir yanlış çift dener.)
    // Her beklemenin kendi catch'i var: yarışı kaybedenin sonradan gelen zaman aşımı reddi
    // işlenmemiş kalırsa Node süreci çöker.
    await Promise.race([
      cont.waitFor({ state: 'visible', timeout: 3000 }).catch(() => {}),
      page.getByText('Canların bitti').waitFor({ timeout: 3000 }).catch(() => {}),
    ]);
  }
  check('Canlar bitince "Oyun Bitti" ekranı geliyor', gameOver);
  if (gameOver) {
    await shot(page, '05-oyun-bitti');
    await page.getByRole('button', { name: /Tekrar Dene/i }).click();
    await settle(page);
    check('"Tekrar Dene" canları 5\'e sıfırlıyor', (await page.getByLabel('5 can kaldı').count()) > 0);
  }

  const csp1 = await page.evaluate(() => window.__cspViolations);
  check('CSP ihlali yok (mobil)', csp1.length === 0, csp1.slice(0, 3).join(' | '));
  check('Konsol hatası yok (mobil)', errors.length === 0, errors.slice(0, 3).join(' | '));

  // ===================== Geniş masaüstü penceresi =====================
  const wide = await newPage(browser, { width: 1280, height: 800 });
  // Aynı veriyi kullanmak için LocalStorage'ı taşı.
  const storage = await page.evaluate(() => JSON.stringify(localStorage));
  await wide.page.goto(URL);
  await wide.page.evaluate((s) => {
    for (const [k, v] of Object.entries(JSON.parse(s))) localStorage.setItem(k, v);
  }, storage);
  await wide.page.reload();
  await openSetMode(wide.page, 'Test Seti', 'Akış');
  await wide.page.locator('[data-feed-card]').first().waitFor();
  await settle(wide.page, 700);
  const layout = await wide.page.evaluate(() => {
    const col = document.querySelector('[data-feed-card] > div').getBoundingClientRect();
    const rail = document.querySelector('[aria-label="Kelimeyi göster"]').getBoundingClientRect();
    const exit = document.querySelector('[aria-label="Akıştan çık"]').getBoundingClientRect();
    return { colW: col.width, colL: col.left, colR: col.right, railR: rail.right, exitL: exit.left };
  });
  check('Geniş pencerede kart içeriği ortalanmış dar sütunda', layout.colW <= 448 && layout.colL > 300, `genişlik ${layout.colW}`);
  check(
    'Eylem rayı ve çıkış düğmesi sütunun içinde',
    layout.railR <= layout.colR + 1 && layout.exitL >= layout.colL - 1
  );
  await shot(wide.page, '06-genis-pencere');

  // Yandaki siyah boşlukta tekerlek de akışı kaydırmalı; oraya tıklamak ok tuşlarını bozmamalı.
  const gutterStart = await feedIndex(wide.page);
  await wide.page.mouse.move(120, 400);
  await wide.page.mouse.wheel(0, 120);
  await settle(wide.page, 1200);
  check('Yan boşlukta tekerlek akışı kaydırıyor', (await feedIndex(wide.page)) === gutterStart + 1);
  await wide.page.mouse.click(120, 400);
  await wide.page.keyboard.press('ArrowDown');
  await settle(wide.page, 1000);
  check('Yan boşluğa tıkladıktan sonra ok tuşları çalışıyor', (await feedIndex(wide.page)) === gutterStart + 2);
  const csp2 = await wide.page.evaluate(() => window.__cspViolations);
  check('CSP ihlali yok (geniş)', csp2.length === 0, csp2.slice(0, 3).join(' | '));
  check('Konsol hatası yok (geniş)', wide.errors.length === 0, wide.errors.slice(0, 3).join(' | '));
} finally {
  await browser.close();
  server.kill();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} kontrol geçti (${BROWSER}).`);
if (failed.length) {
  console.log('Başarısız:', failed.map((f) => f.name).join('; '));
  process.exit(1);
}
