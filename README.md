# Kelime Ustası

Kendi kelime listelerinle çalıştığın, oyunlaştırılmış bir öğrenme uygulaması. Hiçbir soru
uygulamaya gömülü değildir: listeni JSON/CSV dosyası olarak yüklersin ya da `Kelime - Tanım`
satırları halinde yapıştırırsın.

- **Akış** — TikTok tarzı dikey kaydırma: anlatım kartları ve sorular karışık gelir, can yok, akış bitmez.
- **Kartlar** — 3D çevrilen kartlar, Leitner kutularıyla aralıklı tekrar.
- **Test** — 5 can; çoktan seçmeli, yazılı ve eşleştirme soruları.
- XP, günlük hedef ve seri (art arda çalışılan gün) takibi.

Tüm veriler yalnızca senin bilgisayarında tutulur; uygulama internete bağlanmaz.

---

## Mac'e kurulum

### 1. İndir

1. Bu deponun **Actions** sekmesine git → en üstteki yeşil tikli **“Mac uygulaması”** çalışmasını aç.
2. Sayfanın altındaki **Artifacts** bölümünden **`KelimeUstasi-mac`** dosyasını indir (GitHub'a giriş yapmış olman gerekir).
3. İnen `.zip`'i aç; içinden `KelimeUstasi-…-universal.dmg` çıkar.

> Bir sürüm etiketi (`v1.0.0` gibi) yayımlandıysa `.dmg`'yi doğrudan **Releases** sayfasından da indirebilirsin.

Tek dosya hem **Apple Silicon (M1/M2/M3/M4)** hem **Intel** Mac'lerde çalışır. En az **macOS 11 Big Sur** gerekir.

### 2. Kur

`.dmg`'ye çift tıkla ve açılan pencerede **Kelime Ustası**'nı **Uygulamalar** (Applications) klasörüne sürükle.

### 3. İlk açılış (yalnızca bir kez)

Uygulama Apple geliştirici sertifikasıyla imzalanmadığı için macOS ilk açılışta
*“Kelime Ustası açılamadı; Apple, kötü amaçlı yazılım içermediğini doğrulayamıyor”*
benzeri bir uyarı gösterir. Bu beklenen bir durumdur:

**macOS 15 Sequoia ve sonrası**
1. Uygulamayı bir kez açmayı dene, uyarıda **Bitti**'ye bas.
2. **Sistem Ayarları › Gizlilik ve Güvenlik**'i aç, aşağı kaydır.
3. *“Kelime Ustası engellendi…”* satırındaki **Yine de Aç**'a bas, parolanı gir.

**macOS 11–14**
- Uygulamalar klasöründe Kelime Ustası'na **sağ tıkla › Aç**, çıkan pencerede yine **Aç**'a bas.

**Alternatif (Terminal):**
```bash
xattr -dr com.apple.quarantine "/Applications/Kelime Ustası.app"
```

Bundan sonra uygulama Dock'tan ya da Launchpad'den normal şekilde açılır.

> *“Hasar görmüş, Çöp Sepeti'ne taşıyın”* uyarısı alırsan dosya indirme sırasında bozulmuştur;
> `.dmg`'yi yeniden indir. Bu uyarıyı aşmak için yukarıdaki `xattr` komutu da işe yarar.

### Verilerin nerede?

Soru setlerin, ilerlemen ve serin uygulamanın kendi veri klasöründe saklanır
(`~/Library/WebKit/com.erebb.kelimeustasi`). Uygulamayı güncellemek (yeni `.dmg` ile üzerine
kurmak) verilerini silmez. Uygulamayı silip bu klasörü de silersen veriler gider.

### Mac'e özel kısayollar

| Kısayol | İşlev |
| --- | --- |
| ↓ / ↑, Boşluk, Page Down / Up | Akışta sonraki / önceki kart |
| Trackpad'de iki parmakla kaydırma, fare tekerleği | Akışta bir hareket = bir kart |
| Esc | Akıştan çık |
| ⌘C / ⌘V / ⌘X / ⌘A | Metin kutularında kopyala / yapıştır / kes / tümünü seç |
| ⌘M | Pencereyi küçült |
| ⌘W | Pencereyi kapat |
| ⌘Q | Uygulamadan çık |

---

## Soru seti biçimleri

**Düz metin** (her satıra bir çift; ayraç ` - `, sekme ya da `: `):
```
Ephemeral - Kısa süreli, geçici
Ubiquitous - Her yerde bulunan
```

**JSON** (anahtar adları esnek: `question`/`word`/`front`/`soru`/`kelime` ve `answer`/`definition`/`back`/`cevap`/`tanim`; isteğe bağlı `hint`/`ipucu`):
```json
[
  { "kelime": "Ephemeral", "tanim": "Kısa süreli, geçici", "ipucu": "Kelebeklerin ömrü" },
  { "word": "Ubiquitous", "definition": "Her yerde bulunan" }
]
```

**CSV** (başlık satırıyla):
```csv
Soru,Cevap
Ephemeral,"Kısa süreli, geçici"
```

---

## Geliştirme

Gereken: Node.js 22+. Masaüstü uygulaması için ayrıca Rust.

```bash
npm install
npm run dev          # tarayıcıda: http://localhost:5173
npm run build        # dist/ üretim derlemesi
npm run e2e          # uçtan uca test (E2E_BROWSER=webkit|chromium|firefox)
```

### Mac uygulamasını kendi Mac'inde derlemek

```bash
xcode-select --install                                   # Xcode komut satırı araçları
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh   # Rust
npm install
npm run app:dev                                          # pencerede canlı geliştirme
npm run app:build                                        # yalnız bu Mac'in mimarisi için .dmg
```

Hem Intel hem Apple Silicon için tek dosya:
```bash
rustup target add aarch64-apple-darwin x86_64-apple-darwin
npm run app:build:universal
```

Çıktı: `src-tauri/target/…/release/bundle/dmg/`.

Her push'ta GitHub Actions (`.github/workflows/macos.yml`) uygulamayı macOS'ta derler, mimarisini
ve imzasını doğrular, açılışta çökmediğini test eder, uçtan uca testleri Safari motorunda (WebKit)
çalıştırır ve `.dmg`'yi artefakt olarak yükler. `v*` etiketi atıldığında `.dmg` bir GitHub
Release'e eklenir.

### Yapı

```
src/                 React ön ucu (tüm uygulama burada)
src-tauri/           macOS kabuğu (Tauri 2): pencere, Türkçe menü, ikon, paketleme
e2e/smoke.mjs        Uçtan uca test
scripts/             İkon üretimi
```
