# Kelime Ustası — çalışma notları

Kullanıcının kendi sınavlarına çalışmak için kullandığı kişisel çalışma uygulaması (Vite + React +
TS, Tauri ile Mac uygulaması). Kullanıcıyla Türkçe konuşulur. Kullanıcı izin istenmemesini,
işin doğrudan yapılmasını istiyor ("İzin isteme benden direkt yap").

## İçerik kuralları (KALICI — tüm dersler ve sonraki tüm içerikler için)

1. **Sınav odaklı.** Program sınava hazırlanmak için. Sorular ve bilgi kartları sınavda çıkabilecek
   bilgiye göre hazırlanır:
   - Önce slaytlardaki **tablolar** ve **kalın yazılmış** ifadeler; sonra tanımlar, sayısal değerler,
     sınıflamalar, karşılaştırmalar, örnek organizmalar/ilaçlar, yan etkiler, mekanizmalar.
   - Soru tipleri sınav sorusu gibi: "hangisi doğrudur", "hangisi DEĞİLDİR", tablodan değer okuma,
     eşleştirme, hesaplama (slayttaki örnek çözümler).
   - Çeldiriciler aynı konudan ve inandırıcı olmalı (komşu tablo satırları, karıştırılan terimler).
   - Her sorunun açıklaması (`explanation`) neden doğru olduğunu slayt bilgisiyle söyler; `source`
     kaynağı gösterir: slayt için "Slayt N · …"; ders kitabı/defter için "Plate 1.25 · …", "Table 15.6 · …",
     "Sayfa 30 · …" ya da exercise için "Exercise · <konu> N — <sorunun İngilizce aslı>".
   - Kalın, eğik, altı çizili ya da başında yıldız olan ifadeler önemlidir; önce onlar sorulur.
   - **Exercise soruları** (defterdeki alıştırmalar) mutlaka MCQ olarak eklenir. Cevap boşluğu varsa plate ve
     tablolarla, yoksa standart veteriner anatomi bilgisiyle cevaplanır ve kullanıcıya bu söylenir.
   - Kullanıcı "konu anlatımı" isterse setin `lesson` alanına sınav odaklı anlatım yazılır.
   - Bilgi kartları kısa ve hatırlamaya yönelik: ön yüz terim/kavram, arka yüz sınavda istenen öz bilgi.
   - Slaytta olmayan bilgi eklenmez; slayt kendi içinde çelişkiliyse o nokta sorulmaz.
2. **Dil: Türkçe cümleler, İngilizce ilaç adları ve terimler.**
   - Soru kökleri, şıklar, açıklamalar ve kartlar Türkçe yazılır.
   - **İlaç adları ve ilaç sınıfları İngilizce kalır**: vancomycin, erythromycin, ciprofloxacin,
     aminoglycosides, β-lactams, cephalosporins…
   - **Bilimsel terimler İngilizce kalır** (slayttaki haliyle): MIC, MBC, selective toxicity,
     bacteriostatic, broad-spectrum, superinfection, water activity (aw), psychrotrophs, plasmolysis,
     D-value, proofreading…
   - Organizma adları Latince (Staphylococcus aureus, Bacillus polymyxa…).
   - Türkçe ekler kesme işaretiyle: vancomycin'in, MIC'in, 50S'e.
   - Gerekirse az bilinen terimin yanına parantez içinde kısa Türkçe karşılık: turbidity (bulanıklık).
3. XP, seri (streak), can yok — kullanıcı kendisi için kullanıyor. Dersler ayrı tutulur.

## İçerik dosyaları

- `content/*.json`: `{ "name", "items": [...] }`. Öğeler:
  - `{ "id", "type": "mcq", "question", "options", "answer" (şıkla birebir aynı metin), "explanation", "source" }`
  - `{ "id", "type": "card", "front", "back", "source" }`
- İsteğe bağlı `"lesson": [{ "title", "body", "source" }]` = konu anlatımı. `body` biçimi: boş satır yeni
  blok, `- ` madde, `| a | b |` tablo (ilk satır başlık), `! ` ile başlayan blok "Sınavda" kutusu, `### `
  ara başlık, `**kalın**` (bkz. `src/components/RichText.tsx`). Ara başlıkları büyük harfe çevirme:
  sayfa dili `tr` olduğu için İngilizce terimlerde "İ" sorunu çıkar.
- `id` her öğede sabit ve set içinde benzersiz (q01…, c01…). Soru kimliği = `<set anahtarı>:<id>`;
  tekrar (SRS) ilerlemesi buna bağlı. Bir öğeyi düzeltirken id'sini değiştirme; yeni öğeye yeni id ver.
- Dersler: Mikrobiyoloji (`mikrobiyoloji-hafta-*.json`), Topografik Anatomi (`topografik-*.json`: damarlar,
  lenf, sinirler, govde, klinik).
- Uygulamaya ekleme: `src/content/seed.ts` → `BUNDLED_PACKS`. Yeni hafta = yeni set girdisi
  (yeni `key`, `version: 1`). **Var olan bir setin içeriği değiştiğinde `version` bir artırılır**;
  uygulama kullanıcının düzenlemediği kopyayı açılışta günceller.
- Doğrulama: her cevap şıklarda olmalı, şık/soru tekrarı olmamalı, her MCQ'da açıklama ve kaynak olmalı.

## Geliştirme

- `npm run build`, uçtan uca test: `node e2e/smoke.mjs` (yerelde Chromium; CI'da macOS'ta WebKit).
- CI: `.github/workflows/macos.yml` (WebKit e2e + universal .dmg). `v*` etiketi Release yayınlar;
  etiket `package.json` sürümüyle aynı olmalı.
- Commit'ler `claude/gamified-learning-app-hr183v` dalına.
