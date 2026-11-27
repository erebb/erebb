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
     her zaman "Slayt N · …" biçiminde.
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
- `id` her öğede sabit ve set içinde benzersiz (q01…, c01…). Soru kimliği = `<set anahtarı>:<id>`;
  tekrar (SRS) ilerlemesi buna bağlı. Bir öğeyi düzeltirken id'sini değiştirme; yeni öğeye yeni id ver.
- Uygulamaya ekleme: `src/content/seed.ts` → `BUNDLED_PACKS`. Yeni hafta = yeni set girdisi
  (yeni `key`, `version: 1`). **Var olan bir setin içeriği değiştiğinde `version` bir artırılır**;
  uygulama kullanıcının düzenlemediği kopyayı açılışta günceller.
- Doğrulama: her cevap şıklarda olmalı, şık/soru tekrarı olmamalı, her MCQ'da açıklama ve kaynak olmalı.

## Geliştirme

- `npm run build`, uçtan uca test: `node e2e/smoke.mjs` (yerelde Chromium; CI'da macOS'ta WebKit).
- CI: `.github/workflows/macos.yml` (WebKit e2e + universal .dmg). `v*` etiketi Release yayınlar;
  etiket `package.json` sürümüyle aynı olmalı.
- Commit'ler `claude/gamified-learning-app-hr183v` dalına.
