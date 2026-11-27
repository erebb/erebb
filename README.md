# Kelime Ustası

Derslerini kendin düzenlediğin bir çalışma uygulaması: her dersin altında haftalık setler,
her sette sınav tipi sorular ve bilgi kartları. Puan, seri ya da can yok — yalnızca sorular,
cevaplar ve açıklamalar.

- **Soru çöz** — şıklı sınav soruları; her cevaptan sonra doğru şık, açıklama ve slayt kaynağı.
  Sonunda puan, yanlışların listesi ve **“Yanlışları tekrar çöz”**. Soru sayısı seçilebilir (10/20/40/tümü).
- **Göz at** — tüm soru ve kartlar listede (filtre + arama); birine tıklayıp tek tek, önceki/sonraki ile
  gezersin. Cevap “Cevabı göster” ile ya da bir şıkka dokununca açılır; istersen “Cevaplar açık”.
- **Kartlar** — bilgi kartları (ya da soru → cevap kartları) 3D çevrilir; Leitner kutularıyla aralıklı tekrar,
  “Zor” işaretlenen kart aynı oturumda geri gelir.
- **Akış** — TikTok tarzı dikey kaydırma; anlatım kartları ve sorular karışık, bitmez.
- **Konu anlatımı** — konu anlatımı olan setlerde sınav için okunacak bölümler: içindekiler, tablolar,
  “Sınavda” kutuları; sonunda tek dokunuşla o setin sorularına geçilir.

Her mod tek bir sette ya da **“Tüm ders”** ile dersin bütün setlerinde çalışır.

**Hazır içerik:** Uygulama iki dersle gelir:
- **Mikrobiyoloji** — Hafta 7 (mikrobiyal büyümeyi etkileyen faktörler) ve Hafta 8 (antimikrobiyaller)
  slaytlarından 164 sınav sorusu ve 58 bilgi kartı.
- **Topografik Anatomi** — damarlar, lenf düğümleri, sinirler, gövde topografisi ve klinik uygulamalar
  (boynuz anestezisi, enjeksiyon yerleri); konu anlatımı, defterdeki exercise soruları dahil 129 sınav sorusu
  ve 40 bilgi kartı.

Sorular Türkçe, ilaç adları ve bilimsel terimler İngilizce; tablolara ve kalın/eğik yazılmış kavramlara ağırlık
verildi, her sorunun açıklaması ve kaynağı (slayt, plate, tablo ya da exercise numarası) var. İçerik
`content/` klasöründeki JSON dosyalarıdır; bir dersi silersen geri gelmez. Uygulama güncellendiğinde,
düzenlemediğin hazır setler yeni içerikle yenilenir; tekrar ilerlemen korunur.

Tüm veriler yalnızca senin bilgisayarında tutulur; uygulama internete bağlanmaz.

---

## Mac'e kurulum

### 1. İndir

**[Releases](https://github.com/erebb/erebb/releases/latest)** sayfasından **`KelimeUstasi-…-mac.dmg`** dosyasını indir.

Tek dosya hem **Apple Silicon (M1–M4)** hem **Intel** Mac'lerde çalışır. En az **macOS 11 Big Sur** gerekir.

> Henüz yayımlanmamış en son derlemeyi denemek istersen: **Actions** sekmesi → en üstteki yeşil tikli
> **“Mac uygulaması”** çalışması → sayfanın altındaki **Artifacts** → `KelimeUstasi-mac`. Bunun için
> GitHub'a giriş yapmış olman gerekir ve bu dosyalar 90 gün sonra silinir; kalıcı bağlantı Releases'tir.

### 2. Kur

`.dmg`'ye çift tıkla ve açılan pencerede **Kelime Ustası**'nı **Uygulamalar** (Applications) klasörüne sürükle.

Uygulamayı **ilk kez açmadan önce mutlaka Uygulamalar'a kopyala.** Doğrudan `.dmg`'nin içinden ya da
İndirilenler'den açarsan macOS onu geçici, salt okunur bir konumdan çalıştırır ve aşağıdaki onay
adımı kalıcı olmaz.

### 3. İlk açılış (yalnızca bir kez)

Uygulama Apple geliştirici sertifikasıyla imzalanmadığı için macOS ilk açılışta
*“Kelime Ustası açılamadı; Apple, kötü amaçlı yazılım içermediğini doğrulayamıyor”*
benzeri bir uyarı gösterir. Bu beklenen bir durumdur.

**macOS 15 Sequoia ve sonrası**
1. Uygulamalar'dan Kelime Ustası'nı açmayı dene. Uyarıda **Bitti**'ye bas (**Çöp Sepetine Taşı**'ya değil).
2. **Sistem Ayarları › Gizlilik ve Güvenlik**'i aç, en alta kaydır.
3. *“Kelime Ustası, Mac'inizi korumak için engellendi”* satırındaki **Yine de Aç**'a bas ve parolanı gir.

   Bu düğme yalnızca engellenen bir açılış denemesinden sonra, yaklaşık bir saat boyunca görünür.
   Görmüyorsan 1. adımı tekrarla.

**macOS 11–14**
- Uygulamalar klasöründe Kelime Ustası'na **Control tuşuna basılı tutarak tıkla** (ya da sağ tıkla) **› Aç**,
  çıkan pencerede yine **Aç**'a bas.

**Alternatif (Terminal, her sürümde):**
```bash
xattr -dr com.apple.quarantine /Applications/Kelime*.app
```

Bundan sonra uygulama Dock'tan ya da Launchpad'den normal şekilde açılır.

> *“Hasar görmüş, Çöp Sepeti'ne taşıyın”* uyarısı alırsan dosya indirme sırasında bozulmuştur;
> `.dmg`'yi yeniden indir ya da yukarıdaki `xattr` komutunu çalıştır.

### Güncelleme

Yeni `.dmg`'yi indir, Kelime Ustası'nı Uygulamalar'a sürükle ve **Değiştir**'i seç. Soru setlerin ve
ilerlemen korunur. Her yeni sürüm macOS için yeni bir uygulama sayıldığından ilk açılış onayını
(yukarıdaki 3. adım) bir kez daha vermen gerekir.

### Verilerin nerede?

Soru setlerin, ilerlemen ve serin uygulamanın kendi veri klasöründe saklanır
(`~/Library/WebKit/com.erebb.kelimeustasi`). Uygulamayı güncellemek verilerini silmez. Uygulamayı
silip bu klasörü de silersen veriler gider.

### Mac'e özel kısayollar

| Kısayol | İşlev |
| --- | --- |
| 1–4 ya da A–D · Enter | Soru çözerken şık seç · devam et |
| ← / → · Boşluk | Göz atarken önceki / sonraki · cevabı aç/kapat |
| ↓ / ↑, Boşluk, Page Down / Up | Akışta sonraki / önceki kart |
| Trackpad'de iki parmakla kaydırma, fare tekerleği | Akışta bir hareket = bir kart |
| Esc | Akıştan çık · göz atmada listeye dön |
| ⌘C / ⌘V / ⌘X / ⌘A | Metin kutularında kopyala / yapıştır / kes / tümünü seç |
| ⌘M | Pencereyi küçült |
| ⌘W | Pencereyi kapat |
| ⌘Q | Uygulamadan çık |

---

## İçe aktarma biçimleri

Ana ekrandaki **İçe aktar** ya da bir dersin içindeki **Bu derse set ekle** ile:

**Düz metin** (bilgi kartı; her satıra bir çift, ayraç ` - `, sekme ya da `: `):
```
Ephemeral - Kısa süreli, geçici
Ubiquitous - Her yerde bulunan
```

**CSV** (başlık satırıyla):
```csv
Soru,Cevap
Ephemeral,"Kısa süreli, geçici"
```

**JSON — kart ve şıklı sorular karışık** (anahtar adları esnek: `question`/`soru`/`front`/`kelime`,
`answer`/`cevap`/`back`/`tanim`, `options`/`secenekler`, `explanation`/`aciklama`, `source`/`kaynak`):
```json
[
  { "type": "card", "front": "D-value", "back": "Canlı sayısının 10 kat azalması için geçen süre", "source": "Slayt 11" },
  {
    "type": "mcq",
    "question": "Klinik olarak kullanılan tek monobactam hangisidir?",
    "options": ["Aztreonam", "Imipenem", "Meropenem", "Methicillin"],
    "answer": "Aztreonam",
    "explanation": "The only monobactam used clinically is aztreonam.",
    "source": "Slayt 11"
  }
]
```
`answer` şıklardan birinin metni, `"B"` gibi bir harf ya da sıfırdan başlayan bir sıra numarası olabilir.

**JSON — ders paketi** (bir dersi tüm setleriyle tek seferde ekler; aynı adlı ders varsa setler ona eklenir):
```json
{
  "course": "Mikrobiyoloji",
  "sets": [
    {
      "name": "Hafta 9",
      "items": [],
      "lesson": [{ "title": "Konu başlığı", "body": "Paragraf\n\n- madde\n\n! Sınavda çıkar", "source": "Slayt 3" }]
    }
  ]
}
```
(`items` dizisine yukarıdaki gibi kart ve soru öğeleri gelir. `lesson` isteğe bağlıdır ve konu anlatımı olur:
`body` içinde boş satır yeni blok, `- ` madde, `| a | b |` tablo, `! ` ile başlayan blok “Sınavda” kutusu,
`### ` ara başlık, `**kalın**` vurgu.)

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
çalıştırır ve `.dmg`'yi artefakt olarak yükler.

**Sürüm yayımlamak:** `package.json`'daki `version`'ı artır (uygulamanın sürümü oradan okunur),
commit'le ve aynı sürümle bir etiket at — `git tag v1.0.1 && git push origin v1.0.1`. İş akışı
etiketle sürümün eşleştiğini denetler ve `.dmg`'yi bir GitHub Release'e ekler.

### Yapı

```
src/                 React ön ucu (tüm uygulama burada)
content/             Uygulamayla gelen ders içeriği (JSON) — kodda soru yok
src-tauri/           macOS kabuğu (Tauri 2): pencere, Türkçe menü, ikon, paketleme
e2e/smoke.mjs        Uçtan uca test
scripts/             İkon üretimi
```
