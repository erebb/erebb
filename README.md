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
  “Sınavda” kutuları; sonunda tek dokunuşla o setin sorularına geçilir. Kaldığın bölüm hatırlanır
  (**“Kaldığın yerden devam et”**).

Her mod tek bir sette ya da **“Tüm ders”** ile dersin bütün setlerinde çalışır.

**Odak için tasarlandı:** sakin, düşük doygunlukta renkler; renk yalnız anlam taşır (yeşil = doğru,
kırmızı = yanlış, altın = “Sınavda”). Büyük harfli düğmeler, zıplayan animasyonlar ve süs öğeleri yok.
Yazı tipi okunaklılık için tasarlanmış **Atkinson Hyperlegible Next** (I/l/1 ve O/0 karışmaz). Uzun metinler
sola hizalı ve okunaklı satır uzunluğunda. **Açık / Koyu / Sistem** tema ve **tam ekran** (her çalışma
ekranının sağ üstündeki düğme ya da ⌃⌘F) var; ses efektleri varsayılan olarak kapalı (ana ekranın altından
açılır). macOS'ta “Hareketi azalt” açıksa animasyonlar da kapanır.

**İlerleme kaydedilir:** her sorunun kaç kez çözüldüğü, doğru/yanlış sayısı saklanır. Ders sayfasında her
setin ve “Tüm ders”in altında *“x/y çalışıldı · n doğru · m yanlış”* çizgisi görünür; **Soru çöz**'e
başlarken **Hepsi / Çözülmemiş / Yanlışlarım** seçilebilir. Uygulamayı kapatıp açınca hepsi yerinde durur.

**Hazır içerik:** Uygulama iki dersle gelir:
- **Mikrobiyoloji** — Hafta 7 (mikrobiyal büyümeyi etkileyen faktörler) ve Hafta 8 (antimikrobiyaller)
  slaytlarından 184 sınav sorusu ve 63 bilgi kartı. Hafta 8'de slaytlardaki bütün tabloların toplandığı
  bir **“Tablolar”** konu anlatımı ve tablolardan sorular var.
- **Topografik Anatomi** — damarlar, lenf düğümleri, sinirler, gövde topografisi ve klinik uygulamalar
  (boynuz anestezisi, enjeksiyon yerleri); konu anlatımı, defterdeki exercise soruları dahil 129 sınav sorusu
  ve 40 bilgi kartı.

Sorular Türkçe, ilaç adları ve bilimsel terimler İngilizce; tablolara ve kalın/eğik yazılmış kavramlara ağırlık
verildi, her sorunun açıklaması ve kaynağı (slayt, plate, tablo ya da exercise numarası) var. İçerik
`content/` klasöründeki JSON dosyalarıdır; bir dersi silersen geri gelmez. İçerik güncellendiğinde,
düzenlemediğin hazır setler yeni içerikle yenilenir; ilerlemen korunur.

**Kendini günceller:** depoya yapılan her başarılı commit GitHub'da yeni bir sürüm yayımlar. Uygulama her
açılışta son sürüme bakar; yeni ya da düzeltilmiş soru setlerini hemen indirir (yeniden kurmadan) ve Mac
uygulamasının kendisi daha yeniyse onu da indirip kurar (bkz. [Güncelleme](#güncelleme)).

Tüm verilerin (setler, ilerleme) yalnızca senin bilgisayarında tutulur ve hiçbir yere gönderilmez. Uygulama
internete yalnızca güncelleme için çıkar ve yalnızca bu deponun GitHub'daki herkese açık dosyalarını okur;
internet yoksa gömülü içerikle normal çalışır.

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

Kendiliğinden olur — bir şey yapman gerekmez. Uygulama her açılışta GitHub'daki son sürümü denetler:

- **Yeni içerik** (yeni hafta, düzeltilen sorular) hemen yüklenir; altta *“Yeni içerik yüklendi: …”* yazar.
  Senin düzenlediğin setlere dokunulmaz.
- **Uygulamanın yeni sürümü** arka planda indirilip kurulur (*“Yeni sürüm indiriliyor · %…”*). Bitince
  *“Sürüm X yüklendi”* yazar: **Şimdi başlat**'a basarsan hemen, basmazsan bir sonraki açılışta yeni sürüm
  açılır. Otomatik kurulum yapılamazsa *“Yeni sürüm var”* bildirimi ve **İndir** düğmesi çıkar.

Hangi sürümü kullandığın ana ekranın en altında yazar (*“Kelime Ustası · sürüm 1.1.N”*).

> **v1.0.0'ı kurduysan:** o sürümde güncelleyici yoktu. [Releases](https://github.com/erebb/erebb/releases/latest)
> sayfasından en son `.dmg`'yi **bir kez** elle kur (Uygulamalar'a sürükle → **Değiştir**); bundan sonrası
> otomatik. Soru setlerin ve ilerlemen korunur. Elle kurulan her `.dmg` için ilk açılış onayını
> (yukarıdaki 3. adım) bir kez daha vermen gerekebilir.

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
| ⌃⌘F (ya da fn+F) | Tam ekran aç / kapat (menüde Görünüm › Tam Ekran) |
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

**Sürümler kendiliğinden yayımlanır:** `main`'e ya da çalışma dalına yapılan her push'ta testler ve
derleme yeşilse iş akışı `v<major.minor>.<çalışma no>` (örn. `v1.1.42`; `major.minor` `package.json`'dan)
sürümünü GitHub Release olarak yayımlar ve en yeni 5 sürüm dışındakileri siler. Uygulamalar açılışta bu
sürümün içeriğini (`content/manifest.json`) ve — imza anahtarı tanımlıysa — imzalı güncelleme paketini
(`latest.json`, `KelimeUstasi.app.tar.gz`) okur. Elle `v*` etiketi atmak da hâlâ o sürümü yayımlar.

**Güncelleme imzası:** Mac güncelleyicisi yalnızca imzalı paketi kurar. Açık anahtar
`src-tauri/tauri.conf.json`'da; özel anahtar depoda **değil**, GitHub'da
*Settings › Secrets and variables › Actions* altında `TAURI_SIGNING_PRIVATE_KEY` adlı secret olarak durur.
Secret yoksa sürüm yine yayımlanır ama uygulama kendini kuramaz, yalnızca “Yeni sürüm var” der.

### Yapı

```
src/                 React ön ucu (tüm uygulama burada)
content/             Uygulamayla gelen ders içeriği (JSON) — kodda soru yok;
                     manifest.json hangi setin hangi sürümde olduğunu söyler
src-tauri/           macOS kabuğu (Tauri 2): pencere, Türkçe menü, ikon, paketleme
e2e/smoke.mjs        Uçtan uca test
scripts/             İkon üretimi
```
