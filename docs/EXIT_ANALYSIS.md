# Çıkış Adli-Analizi — Stop/TP Anatomisi ve Mekanizma Testleri (2026-07)

## EK — 2. tur: maliyet modeli + saat/pencere kuralları (KABUL edilenler)

Kullanıcının bulgu listesi üzerine üç yeni motor yeteneği eklendi (maliyet
modeli, blackout_hours, sl_tighten) ve 17 hücrelik eski-vs-yeni grid'i
MALİYETLİ (spread 0.30$ + slippage 0.05$ + komisyon %0.05 taker) ve IS/OOS
ayrımlı koşuldu. Karar kuralı (kullanıcı): OOS'ta çürüyen dışarı; kalanların
en kârlısı preset olur.

**KABUL (hem IS hem OOS'ta baseline'dan iyi):**
- fvg `blackout_hours=[9,10,11]` → maliyetsiz +748→**+965** (PF 1.35)
- threevol `blackout_hours=[9,10,11]` → +640→**+2247** (PF 1.60) — 09-11 UTC
  tek başına −1393$'lık kara delikti
- london `sweep_window_bars: 12→6` (yalnız ~06:00 girişleri; 07 saati −131$
  veriyordu) → +419→**+756** (PF 8.3) — maliyetli dünyada bile kârlı tek konfig

**RED:** be@1R (3. kez OOS'ta çürüdü), sl_tighten 0.75 (fvg/threevol'de IS'te
çok kötü — dar stop maliyeti büyütür: R-maliyeti ∝ 1/stop-mesafesi),
threevol be1.25 (OOS kötü). NOT: sl_tighten London/QWE motorlarında
uygulanmadı (kendi _make_entry_trade'leri var) — test edilmedi, bilinçli.

**Maliyet gerçeği (taker %0.05 + spread 0.30$):** fvg −1157, threevol −3979,
london −96, qwe ±0. Dar-stoplu yüksek frekanslı stratejiler taker ücretine
dayanmıyor; canlıda düşük ücretli hesap/maker girişleri şart, aksi halde
yalnız london(w6) canlıya uygun. Maliyetler config `costs` bölümünden
girilebilir (varsayılan 0).

**Nihai preset tablosu (maliyetsiz, 1 yıl):**
| Preset | N | WR | PnL | PF | Sh | DD |
|---|---|---|---|---|---|---|
| threevol none+EMA+1:2be+blackout | 94 | %44.4 | **+2247** | 1.60 | 1.42 | %5.0 |
| fvg none+EMA+1:2fix+blackout | 87 | %41.4 | +965 | 1.35 | 1.11 | %3.5 |
| london private, immediate, w6 | 6 | %66.7 | +756 | 8.29 | 1.61 | %0.5 |
| qwe none (değişmedi) | 59 | %45.8 | +661 | 1.39 | 1.05 | %2.5 |
| **toplam** | 246 | | **+4630/yıl (~%46)** | | | |

(Önceki toplam +2468 → **+%88 iyileşme**, tamamı OOS-doğrulamalı kurallardan.)

---

Amaç: dört sabit preset'in HER stop ve HER TP'sini anlamak ("neden stop, neden
TP"), öğrenilen desenlerden çıkış mekanizmaları türetmek ve yalnızca
**out-of-sample doğrulamadan geçenleri** koda işlemek.

## 1. Enstrümantasyon

`Trade`'e eklendi (motor, teşhis amaçlı — işlem mantığını etkilemez):
- `mfe_r` / `mae_r`: işlem açıkken lehte/aleyhte en uç gidiş (R çarpanı)
- `exit_reason`: tp | sl | be | tp1+tp | tp1+be | time | open

278 işlemlik defter (4 preset × 1 yıl) + 6 grafik: `reports/exit_analysis/`.

## 2. Bulgular — stop'lar ve TP'ler NEDEN oluyor?

| Preset | Kayıpların stop öncesi kârı (MFE) | Kazananın acısı (MAE med.) | TP kalitesi |
|---|---|---|---|
| fvg | med. 0.56R; %58'i ≥0.5R, %27'si ≥1R görmüş | 0.42R | MFE−TP ≈ +0.16R → TP doğru yerde |
| threevol | med. 0.29R; ≥1R gören %0 (BE@1R yakalıyor) | 0.40R | +0.13R → doğru yerde |
| london | med. 0.72R; %70'i ≥0.5R, %40'ı ≥1R görmüş | 0.17R | kazanan MFE med. 3.5R (likidite TP) |
| qwe | med. 0.45R; %19'u ≥1R görmüş | 0.49R | kazanan MFE med. 2.4R |

**Dersler:**
1. Stop'ların ana anatomisi **"kâr geri verme"**: girişlerin çoğu başta doğru
   yönde çalışıyor, kilitlenmeyen kâr geri veriliyor (en uç: London'da 5R görüp
   stop olan işlem).
2. Kazananlar **erken belli oluyor** (düşük MAE) — sweep/pullback girişleri
   doğruysa fazla acı çektirmiyor.
3. **TP'ler zaten doğru yerde** — kazananların MFE'si TP'yi medyan ~0.15R
   aşıyor; TP uzatmak kazandırmaz.
4. ThreeVol'ün BE@1R'ı görevini yapıyor (35 işlem 0'da kurtarılmış).

## 3. Mekanizma adayları ve TEST SONUÇLARI (IS %70 → OOS %30)

Bulgulardan türeyen adaylar: BE@0.75/1R, kısmi-TP@0.75/1R (yeni genel
`partial_tp_r` motor özelliği ile).

| Aday | IS (ilk %70) | OOS (son %30, hiç görülmemiş) | Hüküm |
|---|---|---|---|
| fvg be@1R / ptp@* | hepsi baseline'dan KÖTÜ (−58…−208 vs +287) | koşulmadı | **RED (IS'te elendi)** |
| threevol ptp@1R | −53 → **+366** ✓ | +693 → +567 ✗ (baseline'dan kötü) | **RED (OOS tutmadı)** |
| london be@1R | +157 → **+259**, PF 2.0 ✓ | +262 → **−51** ✗ (tek kazanan BE'yle kaçtı) | **RED (OOS çöktü)** |
| qwe be@* | baseline'dan kötü (+565 vs +474/+359) | koşulmadı | **RED (IS'te elendi)** |

## 4. Sonuç — makinenin öğrendiği

**Hiçbir çıkış mekanizması OOS doğrulamasından geçemedi → dört preset'in
mevcut stop/TP yapısı DEĞİŞTİRİLMEDİ.** Bu negatif sonuç değerli ve kesindir:

- Kısmi-TP/BE, WR'ı görsel olarak güzelleştirir (%37→%64) ama bu stratejilerde
  **beklentiyi düşürür**: kaybedenlerden kurtarılan yarım R'ler, kazananlardan
  feda edilen tam R'leri karşılamıyor.
- "Kâr geri verme" deseni gerçek, ama ondan para çıkarmaya çalışan her
  mekanizma ya IS'te ya OOS'ta kaybetti — desen, sağ-kuyruk kazançların
  bedeli; kuyruk kesilince kâr da kesiliyor.
- IS/OOS disiplini olmasaydı `threevol ptp@1R` ve `london be@1R` preset'lere
  girecekti — ikisi de canlıda para kaybettirirdi.

**Kalıcı kazanımlar:** MFE/MAE + exit_reason enstrümantasyonu (gelecek analizler
bedava), genel `partial_tp_r` motor özelliği (config-kapılı, kapalı),
6 grafiklik adli-analiz seti ve bu rapor.

## 5. Doğrulama

Enstrümantasyon regresyonu: 4 preset, 1 yıl → fvg 91/+747.73,
threevol 112/+640.20, london 16/+418.64, qwe 59/+660.99 — enstrümantasyon
öncesiyle birebir (teşhis alanları davranışı değiştirmiyor).

## EK — %1 risk + aylık kârlılık × piyasa bağlamı (2026-07)

**Her işlem %1 risk** (uniform_risk_fraction=0.01, config risk.risk_fraction):
fvg +2202 (DD %6.8) | threevol +2247 (%5.0) | london +1542 (%1.0) |
qwe +1333 (%5.0) → **TOPLAM +7324/yıl (~%73)**.

**Aylık analiz** (grafik: reports/exit_analysis/7_monthly_pnl_context.png):
13 ayın 11'i pozitif. Korelasyonlar (n=13, gösterge niteliğinde): PnL↔günlük
vol +0.23, PnL↔trend-verimliliği −0.19, PnL↔yön ~0 → sistem yön-agnostik,
volatilite sever, tek yönlü verimli trendden çok İKİ YÖNLÜ geniş salınımda
kazanıyor. Örnekler: en iyi ay 2026-04 (+2563; altın yatay −%1.5 ama salınımlı,
verimlilik 0.05 — sweep/pullback cenneti); 2026-01 (+1087; +%13 trend + rekor
vol — momentum kazandı); 2026-06 (+1361; −%12 çöküş — short taraf çalıştı).
En kötü: 2026-03 (−270; −%11 çöküşte fvg/threevol long sinyalleri kesildi,
qwe +66 ile dengeledi) ve sakin yaz ayları ≈ sıfır (2025-07/08, vol 0.65 —
sinyal kıtlığı ama KAYIP YOK: sistem sakin piyasada kenarda duruyor).

**Canlı entegrasyon tamamlandı:** threevol ve london canlı bota eklendi
(--strategy threevol|london). london bias'ı canlıda PrivateBiasProvider ile
otomatik (GARCH; terminal prompt'u yok), kısmi TP iki yarım emir + TP1 sonrası
yazılımsal BE (qwe altyapısı genelleştirildi). threevol: none+EMA+blackout +
yazılımsal BE@1R (be_arm_price state'te persist; 5dk örnekleme yaklaşımı).
TBE tüm preset'lerde kapalı (backtest pariteesi). Stub simülasyonlarıyla
doğrulandı (london 2-emir payload'u, threevol BE-kolu, %1 eşit risk).

## EK — SWING STOP düzeltmesi (2026-07, kullanıcı direktifi)

Kullanıcı haklı bir tasarım eleştirisi yaptı: fvg/threevol stopları motorun
ilk (intraday) tasarımından miras 5M mikro-yapı stoplarıydı (4-13$ =
fiyatın %0.2-0.3'ü) — swing temeliyle çelişir ve ücret/R'ı patlatır.

**Yeni motor yeteneği `swing_stop_1h`:** SL, son ONAYLI 1H fractal swing
dibine/tepesine (+0.25×ATR1H tampon) taşınır; yalnızca genişletir; canlı
trader AYNI statik fonksiyonu kullanır (`BacktestEngine.swing_stop_price`).

**Grid (IS/OOS × maliyet, 1 yıl):**
- fvg + swing stop: **KABUL** — maliyetsiz +2202→+4332 (PF 2.10, WR %51.5),
  taker %0.05'te bile **+3017** (PF 1.72). Stop medyanı 17$→46$ (fiyatın
  ~%1'i), ücret/R ~0.10R'a düştü; whipsaw stoplar da elendi (IS ve OOS'ta
  tutarlı büyük iyileşme).
- threevol + swing stop: **RED** — IS ve OOS'ta zarara döner (+2247→−329
  maliyetsiz). Momentum-patlaması deseni kendi desen-stopunu (3 mumun dibi —
  o da yapısaldır, sadece doğası gereği dar) gerektiriyor; taker ücretinde
  canlıya uygun değildir (maker/düşük ücret şartı devam).

**Nihai (maliyetsiz, %1 risk):** fvg 68/+4332 (PF 2.10) | threevol 94/+2247 |
london 6/+1542 | qwe 59/+1333 → **TOPLAM +9454/yıl (~%95)**.
Taker %0.05 dünyasında: fvg +3017 ✓, london +1121 ✓, qwe ~+90, threevol
−2344 ✗ (yalnız düşük ücretle çalıştırılmalı).

## EK — LİMİT (maker) GİRİŞ modu ve gerçek-maliyet varsayılanı (2026-07)

**Yeni motor yeteneği `limit_entry_bars=W`:** sinyalde market yerine LİMİT
emir — fiyat sinyal kapanışının SPREAD kadar lehte tarafına yazılır (bull:
C−spread = bid). Sonraki W bar içinde fiyat limite değerse dolum (giriş =
limit fiyatı, maker %0.02, spread/slip yok); değmezse sinyal KAÇAR
(doluş oranı raporlanır — dürüst modelleme). Çıkışlar taker kalır (SL/TP
koşullu emirleri market tetiklenir). Canlı bot birebir: place_limit_order +
pending yaşam döngüsü (doldu → aktif; W bar dolmadı → iptal).

**Grid (maliyetli, %1 risk, IS/OOS):**
- fvg(swing): market +3017 → **limit W=3: +3124** (PF 1.79, doluş %88) → KABUL
- threevol: market −2344 → **limit W=3: −21 (başabaş)**, OOS +345 → KABUL
  (en iyi maliyetli varyantı; yine de taker dünyasında kâr merkezi değil)
- W=6, W=3'ten kötü (geç dolumlar kalitesiz).
- Maliyetsiz dünyada market hâlâ önde (fvg 4332 vs 3696) — kaçan işlemler;
  limit modunun amacı gerçek-maliyet dünyasıdır.

**Config artık GERÇEK-MALİYET varsayılanlı:** costs = spread 0.30 /
slippage 0.05 / taker %0.05 / maker %0.02. Kanonik tablo bundan böyle
maliyetlidir:

| Preset | N | WR | PnL (maliyetli) | PF | DD |
|---|---|---|---|---|---|
| fvg swing+limit W3 | 65 | %50.8 | **+3124** | 1.79 | %6.4 |
| london private w6 | 6 | %66.7 | **+1200** | 5.28 | %1.8 |
| threevol limit W3 | 84 | %34.5 | −21 (başabaş) | 1.00 | %9.2 |
| qwe | 59 | %45.8 | −27 (başabaş) | 0.99 | %7.2 |
| **toplam** | 214 | | **+4276/yıl (~%43, gerçek ücretlerle)** | | |

Kâr merkezleri: **fvg + london**. threevol/qwe gerçek taker ücretlerinde
başabaş — portföyde tutulmaları nötr; ücret kademesi düşerse artıya geçerler
(maliyetsiz: threevol +2247, qwe +1333).

## EK — REJİM META-KATMANI (RegimeEngine + entry_gate, 2026-07)

Kullanıcının strateji-karakter analizi ("ThreeVol kaos avcısı / QWE salınım
taşıyıcısı") üzerine motora genel **rejim kapısı** eklendi:
- `RegimeEngine`: nedensel günlük metrikler (20g getiri-vol %, Wilder ADX,
  BB genişliği sıkışması) — hepsi 1 gün gecikmeli, dünün verisiyle.
- `entry_gate` (engine): False barlarda yeni giriş yok (açık işlem etkilenmez).

**Grid hükümleri (tek tek + kombinasyon, IS/OOS, maliyetli):**
- threevol `vol_floor`: **KABUL — 0.9** (IS +267 / OOS +367 / FULL **+634**,
  PF 1.23; başabaştan gerçek kâra). Eşik platosu 0.8–0.9 sağlam (0.8: +600).
  Kullanıcının volatilite-tabanı hipotezi mekanik olarak doğrulandı.
- threevol ADX<40 kapısı tek başına da sağ kaldı (+496) ama floor'dan zayıf;
  kombinasyon (+512) aşırı-filtreleme → yalnız vol_floor preset'e girdi.
- threevol US-seans/haber-saati whitelist: **RED** (OOS −145).
- QWE vol tavanı (1.8/2.0), squeeze-off, bant filtresi: **hepsi RED** —
  OOS'ta base'den kötü; squeeze hiçbir işleme dokunmadı (aylık anlatı,
  işlem-bazlı gerçekle örtüşmedi). QWE değişmedi.

Canlı parite: threevol tick'te aynı RegimeEngine ile vol tabanını kontrol
eder; düşük-vol rejimde "UYKU" loglayıp sinyal aramaz.

**Nihai (gerçek maliyetli, %1):** fvg 65/+3124 · threevol 52/**+634** ·
london 6/+1200 · qwe 59/−27 → **TOPLAM +4931/yıl (~%49)** (önceki +4276).
Tek ortak kasada bileşik: 10k → ~15.3k (1 yıl).

## EK — BREAKEVEN ailesi: 60 backtest, TAMAMEN ELENDİ (2026-08)

Tetikleyici bulgu (`reports/AY_DERIN_ANALIZ.html`): kaybeden işlemlerin
**%62'si stop olmadan önce +0.5R'ye, %45'i +1.0R'ye** gitti. Kazananların
ortalama MAE'si yalnız 0.42R. MFE tabanlı kaba simülasyon BE@0.5R için
**+61R** vaat etti. Bu sayı YANLIŞ çıktı.

### Motor yetenekleri (varsayılan 0 = etkisiz)
- `be_at_r` — BE tetiğini keyfi eşiğe açar (önce rr etiketinde 1.0R'ye sabitti)
- `be_lock_r` — SL'in KONACAĞI seviye: 0 = klasik BE, −0.5 = SL hâlâ 0.5R
  geride (kısmi sıkılaştırma), +0.5 = kâr kilitle

### Tur 1 — tam BE eşik taraması (`scripts/be_sweep.py`, 32 backtest)
Eşikler 0.8 / 1.0 / 1.2 / 1.5 / 2.0 / 2.5 / 3.0 R. **Hiçbiri, hiçbir
stratejide IS+OOS'ta birlikte iyileştirmedi.**

| Strateji | Baz | En kötü BE | En iyi BE |
|---|---|---|---|
| fvg | +62.0R | BE@0.8 → +35.8R | BE@3.0 → +60.9R |
| harmonic | +41.4R | BE@1.0 → **+7.3R** | BE@3.0 → +30.0R |
| threevol | +12.5R | BE@0.8 → +5.3R | BE@1.0 → +12.5R |
| fib | +18.6R | BE@0.8 → +6.6R | BE@2.0 → +15.6R |

**Simülasyon neden yanıldı:** "+1R görüp stop olan işlem BE ile kurtarılır"
varsayımı, o işlemlerin çoğunun 5R hedefe gidecek KAZANANLAR olduğunu
görmüyor. fvg BE@0.8'de 28 BE tetiklendi; hepsi kurtarılmış kaybeden olsa
+28R olurdu, gerçek −26.2R. WR çöküşü aynı hikâye: fvg %38.8→%20.0,
harmonic %28.6→%11.4.

### Tur 2 — yumuşak kilit (`scripts/be_lock_sweep.py`, 28 backtest)
Kilit −0.5R / −0.75R, tetik 1.0–2.5R. Pozitif kilitler taranmadı (tam
BE'den sert oldukları için mantıken kesin daha kötü).

| Strateji | Baz | En iyi kilit | Fark |
|---|---|---|---|
| harmonic | +41.4R | tetik2.0/−0.75 → +31.4R | **−10.0R** |
| threevol | +12.5R | tetik1.0/−0.50 → +8.5R | **−4.0R** |
| fvg | +62.0R | tetik2.5/−0.75 → +63.5R | +1.5R |
| fib | +18.6R | tetik1.5/−0.75 → +19.1R | +0.5R |

**fvg ve fib'in "geçen" adayları KULLANILMADI.** Gerekçe: her ikisinde de
işlem sayısı ve WR hiç değişmiyor (fvg 49→49 %38.8, fib 16→16 %37.5) — fark
1-2 işlemin sonucundan geliyor. 28 kombinasyon taranıp en iyisi seçilince
şansa bu kadar sapma zaten beklenir; bu seçim yanlılığı, sistematik kazanç
değil. En iyimser toplam etki +2.1R (%1.6).

### Neden BE bu sistemde çalışmıyor
Kazananlar ortalama **206 saat** taşınıyor ve yolda derin geri çekilme
yapıyor (74 kazananın 29'unun MAE'si >0.5R). Kaybedenler **62 saatte**
ölüyor. Girişten sonra stop'a dokunan her mekanizma, kazananın salınımını
kaybedenin ölümünden ayırt edemiyor — ikisini birden kesiyor. Edge çıkış
geometrisinde değil, işlemi UZUN taşımakta.

**Karar: `be_at_r` ve `be_lock_r` config'de 0 (kapalı). Hiçbir preset
değişmedi.** Regresyon doğrulaması: taramanın KAPALI satırları bilinen bazı
birebir üretti (62.0+41.4+12.5+18.6 = 134.5R ≈ 134.4R).

## EK — Giriş filtreleri: yön-göreli MTF hizalama da ELENDİ (2026-08)

Aylık analiz "zararlı aylarda momentum yok" diyordu (|1G MACD%| kârlı
aylarda 1.15, zararlı aylarda 0.69). Bunu giriş filtresine çevirme denemesi:

| Aday | Toplam etki |
|---|---|
| \|D1 MACD%\|/ATR% (yön verimliliği) | ayları 2.02× ayırıyor, **işlemleri d=+0.02** |
| H4 EMA dizilim uyumu ≥1 | −28.0R |
| H1 dizilim uyumu ≥1 | −11.2R |
| H4 & H1 birlikte | −41.6R |
| D1 aşırı-uzama dışla | −95.1R |

Hizalamalar **yön-göreli** hesaplandı (short işlemde bearish dizilim = iyi).
Hepsi zarar. **Aylık istatistik işlem seviyesine inmiyor** — kötü aylarda da
büyük kazananlar var, filtre onları da kesiyor.

## EK — Zarar rejimleri: İKİ ayrı ölüm şekli (2026-08)

`scripts/streak_analysis.py` — 4 ardışık-zarar serisi:

| Seri | Ay | R | PnL | İşlem |
|---|---|---|---|---|
| 2026-02→04 | 3 | −9.3R | −3.047$ | 20 |
| 2025-05→06 | 2 | −11.2R | −2.394$ | 14 |
| 2023-05→08 | 4 | −8.5R | −1.145$ | 7 |
| 2022-10→11 | 2 | −7.4R | −929$ | 7 |

| Grup | İşlem | WR | 1G ATR% | Ort. MFE | Ort. süre |
|---|---|---|---|---|---|
| Zarar serileri | 48 | %10 | **2.00** | 1.20R | 51s |
| Tek-ay zararlar | 23 | %4 | **0.96** | 1.67R | 115s |
| Kârlı aylar | 137 | %50 | 1.29 | 2.62R | 128s |

**Seriler YÜKSEK volatilitede, tek-ay zararlar DÜŞÜK volatilitede oluşuyor.**
Aynı olgu değiller. Seri uzunluğu maliyetle ilişkili değil — işlem sayısı
ilişkili (4 aylık seri yalnız −1.145$, 3 aylık seri −3.047$).

### Trend rejimi stop oranını AÇIKLAMIYOR
Kaufman verimlilik oranıyla ay sınıflandırması (`reports/ay_rejim.csv`):

| Rejim | Ay | Pozitif ay | İşlem | Stop oranı | Toplam R |
|---|---|---|---|---|---|
| BOĞA | 10 | %70 | 35 | %51 | +36.6 |
| AYI | 4 | %50 | 23 | %48 | +7.4 |
| YATAY | 27 | %56 | 108 | %56 | +49.2 |

Stop oranı her rejimde %48–57 — fark yok. Her rejim kârlı. En kötü aylar her
rejimden geliyor (2026-03 ayı −6.9R, 2022-11 boğa −5.7R, 2025-06 yatay −8.5R).

### Asıl ayrım: SMA200 filtresi piyasaya ters düştüğünde
| | Ay | Pozitif ay | İşlem | Toplam R | Ay başına |
|---|---|---|---|---|---|
| **UYUMLU** (filtre ↔ piyasa aynı yön) | 37 | %70 | 142 | **+143.8R** | +3.89R |
| **TERS** (zıt yön) | 16 | %31 | 66 | **−9.4R** | −0.59R |

Sistemin tüm kârı uyumlu aylardan geliyor. Zararlı 18 ayın 10'u ters; kârlı
31 ayın yalnız 5'i ters. Mekanizma: SMA200 yavaştır, piyasa döndüğünde filtre
eski yönü göstermeye devam eder (2026-03'te fiyat −%16.6 düşerken filtre
"boğa" diyordu → 7 işlemin 6'sı stop).

**UYARI: bu tablo GERİYE DÖNÜK.** "Ayın gerçek yönü" ancak ay bitince bilinir;
canlıda bu filtre kurulamaz. Teşhis, çözüm değil. Nedensel karşılığı
(SMA200 kesişimine yakınlık = geçiş anı tespiti) henüz test EDİLMEDİ.

## EK — SMA200 geçiş tespiti: nedensel filtre ELENDİ (2026-08)

Bir önceki EK'teki "TERS aylar" bulgusunun (filtre piyasaya ters düştüğünde
16 ay −9.4R, uyumlu 37 ay +143.8R) **canlıda kurulabilir** karşılığı arandı.
`scripts/sma200_transition_test.py` — 25 aday, hepsi shift(1) ile nedensel
(motorun `daily_trend`'iyle aynı disiplin).

| Aday ailesi | En iyi varyant | Toplam etki |
|---|---|---|
| A) SMA200'e uzaklık ≥ X% (geçiş bölgesini dışla) | ≥0.5% | −9.6R |
| B) kesişimden geçen gün ≥ N (taze trendi dışla) | ≥5 gün | −7.4R |
| C) SMA200 eğimi işlem yönünde | ≥0.0% | −40.4R |
| D) A/B/C birleşimleri | uzaklık≥1% & yaş≥20g | −31.0R |
| E) tersi (yalnız SMA200 yakınında işle) | ≤3.0% | −96.9R |
| F) filtre yönü == N-gün momentum | 40 gün | −25.5R |
| G) işlem yönü == N-gün momentum | 40 gün | −25.5R |

**KABUL EDİLEN ADAY YOK.** 25 varyantın hiçbiri IS+OOS'ta birlikte
iyileştirmedi; en iyisi bile −7.4R.

### Bulgunun neden çevrilemediği — kritik nokta
"TERS" ayların geriye dönük olarak −9.4R getirmesine karşılık, aynı
uyumsuzluk **gerçek zamanlı** tespit edildiğinde o işlemler **kârlı**:

| Nedensel TERS alt kümesi | İşlem | Toplam R |
|---|---|---|
| filtre ≠ 10 gün momentum | 73 | **+44.2R** |
| filtre ≠ 20 gün momentum | 56 | **+53.5R** |
| filtre ≠ 40 gün momentum | 40 | **+25.5R** |

Yani "filtre yanılıyor" durumu canlıda tespit edilebiliyor ama o durumdaki
işlemler zarar etmiyor. Aylık TERS istatistiği, ayın sonunda bilinen bir
sonuca göre yapılan gruplamadan doğan **geriye dönük artefakt**; işlem
seviyesinde karşılığı yok.

Bu, aynı desenin dördüncü tekrarı: aylık/rejim düzeyinde çok güçlü görünen
ayrımlar (ADX, |MACD%|, MTF hizalama, SMA200 uyumu) işlem seviyesine
inmiyor. Kötü aylarda da büyük kazananlar var; her filtre onları da kesiyor.

**Config'de hiçbir değişiklik yapılmadı.**

## EK — EŞ-ZAMANLI POZİSYON: kaldıraç kılığında, ELENDİ (2026-08)

Soru: sinyal geldiğinde açık işlem varken de girsek ne olur? Motor iki
TEK-kişilik slot tutuyor ('fvg' ve 'prz'); slot doluyken gelen sinyal
atlanıyor. `scripts/concurrency_lab.py` bu slotları kapasiteli havuza
çevirir (motor bellekte yamanır, diskte hiçbir dosya değişmez).

### Ham sonuç — ilk bakışta çok güçlü
| | İşlem | IS | OOS | Toplam R | Bakiye | MaxDD |
|---|---|---|---|---|---|---|
| N=1 (mevcut) | 210 | +73.3 | +61.1 | +134.4R | 35.991$ | %12.3 |
| N=2 | 330 | +126.4 | +102.2 | +228.6R | 88.054$ | %20.8 |
| N=3 | 436 | +165.1 | +134.4 | +299.5R | 171.854$ | %29.2 |
| N=5 | 620 | +193.6 | +181.8 | +375.5R | 345.235$ | %45.6 |

İşlem başına R korunuyor (0.640 → 0.693 → 0.687 → 0.606) ve IS/OOS birlikte
artıyor. İlk koşuda mekanizma "KABUL" göründü.

### Riske-normalize kıyas — sonucu TERSİNE çevirdi
Her senaryo, maks. düşüşü %12.3'e (mevcut sistemin seviyesi) eşitleyecek
risk oranıyla yeniden koşuldu:

| | Risk/işlem | Bakiye | MaxDD |
|---|---|---|---|
| **N=1** | %1.00 | **35.991$** | %12.3 |
| N=2 | %0.56 | 34.950$ | %12.3 |
| N=3 | %0.38 | 30.658$ | %12.3 |

**Eşit riskte eş-zamanlılık daha KÖTÜ** (N=2 −%3, N=3 −%15).

Kaldıraçla doğrudan kıyas (N=1 defteri, yalnız pozisyon boyutu büyütülerek):

| Senaryo | Bakiye | MaxDD | Bakiye/DD |
|---|---|---|---|
| N=1 risk %2.0 | 114.745$ | %23.2 | 45.1 |
| N=2 risk %1.0 | 88.054$ | %20.8 | 37.5 |
| N=1 risk %3.0 | 326.774$ | %33.0 | 96.0 |
| N=3 risk %1.0 | 171.854$ | %29.2 | 55.4 |

Benzer düşüşte **riski artırmak eş-zamanlılıktan daha çok getiriyor**.

### Neden: mükerrer giriş
| | İşlem | 48 saat içinde aynı yön + %0.2 fiyat yakınlığı |
|---|---|---|
| N=1 | 210 | 7 çift |
| N=2 | 330 | **123 çift** |
| N=3 | 436 | **318 çift** |

İşlem sayısı %57 artarken mükerrer çift **17 kat** artıyor. Ek işlemler yeni
fırsat değil, aynı kurulumu tekrar oynamak. Yeni işlemlerin R/işlem'inin
daha yüksek çıkması (0.785 vs 0.640) da bunu doğruluyor: aynı kazanan
kurulum iki kez alınınca ikisi de kazanıyor.

### Test aracındaki düzeltilen hata
İlk koşuda basılan "KABUL" etiketi YANLIŞTI. Kriter "bakiye oranı ≥ düşüş
oranı" idi; bileşik getiri süperlineer büyüdüğü için bu şart neredeyse her
zaman sağlanır. Kriter riske-normalize kıyasla değiştirildi. Ayrıca
eş-zamanlılık metriği hatalıydı (işlem başına kendini de sayıyordu, N=1'de
"14" gösteriyordu); olay-taraması ile düzeltildi — gerçek değerler:
N=1 ortalama 1.33 tepe 4 · N=2 2.43/6 · N=3 3.39/8.

**Karar: mekanizma ELENDİ. Motor ve config değişmedi.**
Pratik çıkarım: daha çok getiri isteniyorsa doğru yol eş-zamanlılık değil,
`risk.risk_fraction`'ı bilinçli yükseltmek — ama %2 risk maks. düşüşü
%23'e çıkarır ve backtest düşüşü zaten iyimserdir.

## EK — HEDGE (açık işlemin tersi yönde ikinci giriş): ELENDİ (2026-08)

Soru: açık işlem varken ters yönde sinyal gelse hedge olarak alsak ne olur?

### Önce yapısal tespit
Mevcut sistemde hedge **zaten imkânsız**. Günlük SMA200 kapısı
(`xauusd_fvg_engine_v10.py:2710`) ana trende karşı HER sinyali reddeder;
dört stratejinin dördü de aynı filtreyi kullandığı için aynı anda iki yönde
sinyal hiç oluşmaz. Test için kapı YALNIZCA hedge girişinde delindi
(`scripts/hedge_lab.py`). Yani ölçülen şey "kaçırılan hedge fırsatları"
değil, **bilinçli karşı-trend pozisyon açmak**.

### Sonuç
| | İşlem | IS | OOS | Toplam R | Bakiye | MaxDD | Eşit riskte |
|---|---|---|---|---|---|---|---|
| hedge KAPALI | 210 | +73.3 | +61.1 | **+134.4R** | 35.991$ | %12.3 | **36.107$** |
| hedge AÇIK | 244 | +64.1 | +56.0 | +120.1R | 30.978$ | %12.3 | 31.066$ (**−%14**) |

### Temiz ayrışma — ana işlemler hiç etkilenmedi
Hedge işlemleri tek başına: **34 işlem, −14.3R, işlem başı −0.422R**
(30 stop / 4 TP, kazanma oranı %11.8; yön: 28 short / 6 long).

Toplam düşüş (134.4 → 120.1 = −14.3R) hedge işlemlerinin PnL'ine **birebir
eşit**. Yani hedge girişleri ana işlemlerin hiçbirini bozmadı, sırasını
kaydırmadı — saf ek yük olarak geldiler ve saf zarar ettiler.

### Bunun asıl değeri: günlük trend filtresinin ölçülmesi
| | R / işlem | Kazanma |
|---|---|---|
| Trend yönlü (mevcut sistem) | **+0.640** | %35.2 |
| Karşı-trend (hedge) | **−0.421** | %11.8 |

Aradaki fark **1.06 R/işlem**. Bu, `daily_trend_filter`'ın tek başına en net
ölçülmüş katkısıdır: filtre kaldırılsa alınacak işlemler işlem başına 1R'den
fazla kaybettiriyor. Daha önce "trend rejimi stop oranını açıklamıyor"
bulunmuştu (her rejimde %48–57) — bu onunla çelişmez: rejimin KENDİSİ
sonucu açıklamıyor ama işlemin trendle UYUMU açıklıyor.

### Ekonomik ve canlı uyarıları (kayıt için)
- Tek enstrümanda long+short aynı anda net pozisyonu düzleştirir ama HER İKİ
  tarafın spread+komisyonu ödenir. Ücret formülü
  `(maker+taker) × fiyat / stop_mesafesi` olduğu için hedge maliyeti ikiye
  katlar. Risk azaltmaz.
- BingX vadeli işlemlerde aynı sembolde iki yön "hedge mode" gerektirir;
  tek-yön modda ters emir mevcut pozisyonu KAPATIR.

**Karar: ELENDİ. Motor ve config değişmedi.**

## EK — BİLEŞİK HESABI DÜZELTMESİ: sıralı → olay tabanlı (2026-08)

Raporlar portföy bakiyesini ÇIKIŞ SIRASINA göre hesaplıyordu:

    for r in trades.sort_values('exit').r:  bal *= (1 + f*r)

Bu, eş-zamanlı pozisyon varken YANLIŞTIR: bir işlem açıldığında, ondan sonra
kapanacak işlemlerin kârı henüz hesapta yoktur; sıralı yöntem o kârı peşinen
sayıp pozisyonu olduğundan büyük boyutlandırır.

Doğrusu (motorun kendi davranışı): pozisyon GİRİŞ anındaki gerçekleşmiş
bakiyeye göre boyutlanır, kâr/zarar ancak ÇIKIŞ'ta bakiyeye geçer.
`scripts/equity.py` bunu uygular.

### Hata eş-zamanlılıkla büyüyor
| Senaryo | Sıralı (hatalı) | Olay tabanlı (doğru) | Hata |
|---|---|---|---|
| N=1 (mevcut, ort. 1.33 pozisyon) | 35.991$ | **34.586$** | %3.9 |
| N=2 | 88.054$ | 71.661$ | %23 |
| N=3 | 171.854$ | 111.983$ | %53 |
| Limitsiz (ort. 8.5, tepe 37) | **5.894.202$** | **119.582$** | **49 kat** |

### Limitsiz senaryo ayrıca FİNANSE EDİLEMEZ
Gereken kaldıraç (açık pozisyonların toplam notional'ı / bakiye):

| Senaryo | Ortalama | Tepe |
|---|---|---|
| N=1 (mevcut) | 1.4x | 9.3x |
| N=2 | 2.3x | 17.7x |
| N=3 | 3.0x | 22.5x |
| Limitsiz @ %1 | 10.5x | **63.8x** |

Stoplar swing noktalarında olduğu için işlem başına notional bakiyenin ~2
katı; eş-zamanlılıkta toplanır. 63.8x ne BingX'te ne MT5'te finanse edilebilir
— marjin çağrısı gelir. O backtest yaşanamayacak bir senaryoyu simüle ediyor.

### Eş-zamanlılık kararı DEĞİŞMEDİ (güçlendi)
Riske-normalize kıyas, doğru yöntemle (hedef DD %12.3):

| | Risk/işlem | Bakiye |
|---|---|---|
| **N=1** | %1.00 | **34.586$** |
| N=2 | %0.56 | 32.452$ |
| N=3 | %0.38 | 28.235$ |
| Limitsiz | %0.09 | 17.505$ |

### Düzeltilen sistem rakamı
Sistemin bildirilen bakiyesi **35.991$ değil, 34.586$** (−%3.9). Yıl yıl:
2022 +1.975$ · 2023 +2.460$ · 2024 +3.507$ · 2025 +10.235$ · 2026 +6.409$.

**R toplamı (+134.4R), işlem sayısı (208), WR (%35.2), PF (2.00) ve MaxDD
(%12.3) DEĞİŞMEDİ** — hepsi R tabanlıydı ve doğruydu. Değişen yalnız dolar
bileşiği. `scripts/pnl_report.py` ve `scripts/concurrency_lab.py` düzeltildi;
concurrency_lab artık gereken kaldıracı da basıyor.

## EK — SCALP + İŞLEM LİMİTİ YOK: ELENDİ, ve kaldıraç sorunu (2026-08)

En kârlı scalp varyantı (C: dar yapısal stop + 1:3 hedef + 8 saat zaman
çıkışı, MT5 maliyeti) işlem limiti kaldırılarak koşuldu. Motor bellekte
yamandı (concurrency_lab), config bellekte değiştirildi; disk değişmedi.

| Limit | İşlem | Toplam R | Bakiye | Düşüş | **Eşit riskte** | Eş-zaman | Kaldıraç ort/tepe |
|---|---|---|---|---|---|---|---|
| N=1 | 302 | +102.7 | 26.715$ | %10.2 | **20.216$** | 1.12/3 | 3.9x / 54.2x |
| N=2 | 490 | +155.5 | 42.485$ | %21.7 | 19.513$ (−%3.5) | 1.79/5 | 5.9x / 61.1x |
| N=3 | 648 | +201.6 | 61.950$ | %25.4 | 20.603$ (+%1.9) | 2.38/7 | 7.9x / 61.1x |
| Limitsiz | 1443 | **+350.5** | 124.037$ | **%56.5** | **15.869$ (−%21.5)** | 5.84/29 | 18.9x / 117.7x |

Ham R üçe katlanıyor ama eşit riskte DÜŞÜYOR. N=3'ün +%1.9'u gürültü:
N=2 −%3.5 veriyor, sıralama monoton değil. **Swing'deki sonucun aynısı —
eş-zamanlılık edge katmıyor, riski büyütüyor.** (Beşinci tekrar.)

### Eş-zamanlılıktan BAĞIMSIZ bulgu: scalp yüksek kaldıraç istiyor
%1 risk sabit, stop yarıya inince pozisyon iki katına çıkar
(pozisyon = risk / stop). Scalp'in medyan stopu 6.3$, swing'in 15$:

| | Scalp C | Swing |
|---|---|---|
| Medyan kaldıraç (işlem başına) | **4.4x** | 1.3x |
| %95 dilim | **11.4x** | 5.4x |
| En yüksek tek işlem | **38.4x** (stop 0.53$) | — |

Prop firmalar ve brokerlar altında kaldıracı sınırlar (yaygın 1:20–1:100).
Scalp işlemlerinin %5'i 11x'in, biri 38x'in üstünde; limitsiz senaryoda tepe
117.7x — finanse EDİLEMEZ. **Scalp canlıya konmadan önce broker'ın kaldıraç
limiti öğrenilmeli**, yoksa backtestteki işlemlerin bir kısmı hiç açılamaz
ve sonuç geçersiz olur. Swing bu açıdan rahat (medyan 1.3x).

**Karar: ELENDİ. Config'e dokunulmadı (profile=swing, costs=BingX).**

## EK — BIAS FİLTRELERİ: elendi + LOOKAHEAD HATASI bulundu (2026-08)

`scripts/bias_lab.py` — dört bias modu × dört strateji, IS/OOS ayrımıyla.

### Önce: kodda lookahead bulundu ve düzeltildi
`DailyBiasProvider.build_from_1h` D gününün bias'ını **D gününün kendi
kapanışından** türetiyordu (`o = ilk Open`, `c = son Close`, `out[D] = c>o`).
Sabah işlem açarken o günün kapanışı bilinemez — kâhin filtresi.
Düzeltildi: bias bir gün kaydırıldı (D'nin bias'ı = D−1'in yönü).
Doğrulama: 1041/1041 kayıt D−1 ile eşleşiyor; aynı günle tesadüfen uyuşma
%47 (rastgele ~%50). `build_weekly_from_1h` aynı mantıkla eklendi.

Kapsam sorunu da vardı: `daily_bias.json` 245 kayıtla 2025-07'den başlıyordu
→ IS'te sıfır işlem, test bias değil TARİH FİLTRESİ ölçüyordu. Yeniden
üretildi (daily 1041 kayıt / 2021-07→2026-07, weekly 211 kayıt).
`weekly_bias.json` kendi notunda "hindsight" yazıyordu.

**Ana sistem bias kullanmıyor (`bias: "none"`), yayınlanmış hiçbir sonuç
bu hatadan etkilenmedi.**

### Sonuç (düzeltilmiş, nedensel veriyle)
| Strateji | none | daily | weekly | private |
|---|---|---|---|---|
| fvg | **+62.0** | +49.0 | +68.9 ⚠ | +21.1 |
| harmonic | **+41.4** | +9.8 | +13.7 | +21.6 |
| threevol | +12.5 | +12.5 | +8.6 | **+19.7** |
| fib | **+18.6** | +1.0 | +16.9 | +12.0 |

`daily` hiçbir yerde işe yaramadı (harmonic +41.4→+9.8, fib +18.6→+1.0).

**fvg+weekly tuzağı:** toplam +68.9R bazın üstünde ama IS +42.6 (baz +33.8)
iken OOS +26.4 (baz +28.2) — OOS'ta GERİLİYOR. Yalnız toplama bakılsaydı
kabul edilirdi; IS+OOS şartı bunu yakaladı.

### Tek geçen aday da riske-normalize kıyasta elendi
threevol+private: 75→47 işlem, WR %38.7→%46.8, IS +2.7→+8.9, OOS +9.7→+10.9.
Portföy +134.4R → +141.7R (34.586$ → 37.228$) ama düşüş %12.3 → %13.1.

| | İşlem | R | Bakiye | DD | **Eşit riskte** |
|---|---|---|---|---|---|
| mevcut (hepsi none) | 210 | +134.4 | 34.586$ | %12.3 | **34.586$** |
| threevol=private | 182 | +141.7 | 37.228$ | %13.1 | **34.434$ (−%0.4)** |

Ham +7.2R kazanç, düşüş artışıyla tam olarak sıfırlanıyor. Uyarı işareti
zaten vardı: kazancın çoğu IS'te (IS 3.3 kat, OOS yalnız %12).

**Karar: ELENDİ. Config'e dokunulmadı (tüm stratejiler bias="none").**

## EK — VWAP FİLTRESİ: dört çapada da ELENDİ (2026-08)

`scripts/vwap_lab.py` — saatlik / günlük / haftalık / aylık çapa, 210 işlemin
TAMAMI üzerinde, 44 filtre varyantı. VWAP ve σ shift(1) ile nedensel.

### Önce: kendi testimde bulunan hata
İlk tarama 5M verideki **sıfır hacimli barları 1.0** yapıyordu. Veride
519.264 barın **169.129'u (%32.6)** sıfır hacimli (hafta sonu ve seans
kapanışlarında doldurulmuş barlar; 21:00 UTC'de tepe yapıyor). Bu, VWAP'ı
kısmen basit ortalamaya çeviriyor ve ayırt gücünü **yapay olarak
0.145'ten 0.308'e** şişiriyordu. Düzeltildi: sıfır hacimli barlar birikime
katılmaz. Rapor edilen d=0.308 GEÇERSİZ, doğrusu 0.145.

### Ayırt gücü — hiçbiri anlamlı değil
| Çapa | Geçerli | Kazanan z_al | Kaybeden z_al | Cohen d |
|---|---|---|---|---|
| saatlik | 199/210 | 1.382 | 1.157 | +0.119 |
| günlük | 209/210 | 1.398 | 1.216 | +0.145 |
| haftalık | 209/210 | 1.200 | 1.172 | **+0.026** |
| aylık | 210/210 | 1.040 | 0.800 | **+0.209** |

### 44 varyantın hiçbiri geçmedi
| Çapa | En iyi filtre | Toplam (baz +134.4R) |
|---|---|---|
| saatlik | \|z\| ≤ 3.0 | +118.6R (−15.8) |
| günlük | \|z\| ≤ 3.0 | +128.6R (−5.8) |
| haftalık | \|z\| ≤ 3.0 | +134.7R (+0.3) ⚠ |
| aylık | \|z\| ≤ 3.0 | +129.5R (−4.9) |

Haftalık `|z|≤3.0` toplamda +0.3R ile bazın üstünde ama **IS +3.8 / OOS −3.5**
— OOS'ta geriliyor, elendi. Zaten 209 işlemin 204'ünü tutuyor (5 işlem farkı).

### Öğrenilen
Çapa uzadıkça kazanan-kaybeden farkı açılıyor (aylık en yüksek). Sistemin
işlemleri ortalama 206 saat taşındığı için saatlik VWAP o ölçekte gürültü,
aylık anlamlı bir referans. Ama anlamlı olmak kârlı olmayı sağlamıyor.

### Veri notu (VWAP dışına da uzanır)
5M verinin %32.6'sı sıfır hacimli. Hacme dayalı HER gösterge bu veri setinde
şüpheli. Fiyat bazlı göstergeler (EMA/MACD/ATR) etkilenmez ve **sistemin
kendisi hacim kullanmıyor** — yayınlanmış sonuçlar etkilenmedi.

**Karar: ELENDİ. Config'e dokunulmadı.**
## EK — SEANS HİZALAMA İDDİALARININ ÖLÇÜMÜ (2026-08)

`scripts/session_lab.py` — kullanıcının ileri sürdüğü dört seans iddiası
1.274 iş günü (2021-08 → 2026-07) üzerinde ölçüldü. Wilson %95 güven
aralıklarıyla. Seanslar (UTC): Tokyo 00–08, Londra 07–16, NY 12–21.

| İddia | İleri sürülen | Ölçüm | %95 aralık | Sonuç |
|---|---|---|---|---|
| Üç seans aynı hizada | %30 | **%39.4** | 36.8–42.1 | daha GÜÇLÜ |
| Londra = NY | %62 | **%74.5** | 72.0–76.8 | çok daha GÜÇLÜ |
| Tokyo teyit edici | — | fark −1.0 puan | örtüşüyor | gösterilemedi |
| NY ters manipülasyon | %40 | eşiğe bağlı | — | aşağıya bak |

Rastgelelik referansı: üç seansın aynı yönde olması şans eseri %25 olurdu;
%39.4 anlamlı yapı gösteriyor.

### Tokyo'nun teyit değeri yok
| Durum | Londra = NY |
|---|---|
| Tokyo, Londra ile UYUMLU | %74.0 [70.6–77.2] |
| Tokyo, Londra ile TERS | %75.0 [71.4–78.3] |

Güven aralıkları tamamen örtüşüyor. Tokyo'nun yönü Londra–NY uyumu hakkında
bilgi taşımıyor. Tokyo'nun diğer seanslarla uyumu da yazı-tura seviyesinde
(Tokyo=Londra %53.2, Tokyo=NY %51.1) — Londra=NY %74.5 ile kıyaslanınca
Tokyo'nun ayrı bir hayvan olduğu görülüyor.

### "NY manipülasyonu" sıradan oynaklık
NY seansı içinde, seansın nihai yönünün TERSİNE hareket:

| Eşik | Ters | Lehte |
|---|---|---|
| ≥0.10×ATR | %64.2 | **%97.8** |
| ≥0.15×ATR | %50.5 | **%94.7** |
| ≥0.20×ATR | %38.1 | **%90.0** |

%40'ı yakalamak için eşiği 0.20×ATR seçmek gerekir — eşik seçilerek her oran
üretilebilir, bu döngüsel olur. Asıl kanıt karşılaştırmada: LEHTE hareket her
eşikte ~2 KAT daha sık. Gerçek bir manipülasyon deseni olsaydı ters hareketin
daha sık veya daha derin olması gerekirdi; tersi çıkıyor. Bu, bir seans
kapanış yönüne giderken yolda iki yöne de salınmasının doğal sonucu.

### Uyarı: bunlar edge değil, istatistik
Londra 07–16 ile NY 12–21 ÖRTÜŞÜYOR; Londra kapandığında NY'nin bir kısmı
zaten geçmiş oluyor. %74.5 uyum "Londra yukarı kapandıysa NY'de long aç"
demek DEĞİLDİR. İşlem edilebilir sinyale çevirmek ayrı bir test gerektirir.

**Config'e dokunulmadı — bu bir ölçüm, mekanizma değişikliği değil.**

## EK — F2 KLİMAKS+RET ve TERS-MARTİNGALE: ikisi de ELENDİ (2026-08)

Dış kaynaklı bir bot tanımından (MARK 1.8) iki mekanizma test edildi:
`scripts/f2_climax_lab.py`.

### F2 — klimaks + ret filtresi
Klimaks: H1 barının aralığı ≥ K×ATR14. Ret: aynı barda kapanış hareketin
tersine çekilmiş (boğa için kapanış aralığın üst %40'ında ve alt fitil ≥
aralığın yarısı). Filtre: girişten önceki N H1 barında işlem yönünde
klimaks+ret varsa izin ver. Hacim KULLANILMADI (5M verinin %32.6'sı sıfır
hacimli), klimaks aralık tabanlı.

| K | N bar | İşlem | Toplam (baz +134.4R) |
|---|---|---|---|
| 1.5 | 6 | 21 | +15.2R |
| 1.5 | 12 | 35 | +27.6R |
| 2.0 | 12 | 23 | **+30.9R** |

En iyisi 210 işlemin 187'sini kesiyor. Diğer eşiklerde örneklem <20.
**NOT:** bu, F2'nin kendi botlarında işe yaramayacağı anlamına gelmez —
oradaki üretici tek motor (H1 FVG), bizimki dört strateji + günlük SMA200
kapısı; sistem zaten seçici.

### RM — ters-martingale (piramit) boyutlandırma
Taban %1, her ardışık kazançta ×çarpan, %8 tavan, kayıpta tabana dön.

**İLK HESAP HATALIYDI** (sıralı bileşik; sistem ort. 1.33 pozisyon taşıyor).
Olay tabanlı doğru hesap:

| Çarpan | Bakiye | DD | Max risk | Eşit riskte |
|---|---|---|---|---|
| yok (%1) | 34.586$ | %12.3 | %1.00 | **34.586$** |
| ×1.25 | 39.214$ | %12.6 | %3.05 | 37.905$ |
| ×1.50 | 46.508$ | %17.5 | %7.59 | 30.134$ |
| ×2.00 | 51.230$ | %23.6 | %8.00 | **25.196$** |

Sıralı hesapta ×2.00 için 62.587$ çıkmıştı; doğrusu 25.196$ (2.5 kat hata).
×1.25 eşit riskte +%9.6 ama ×1.50/×2.00 negatif — monoton değil, gürültü.

**Neden çalışmıyor:** WR %35'te uzun kazanç serisi oluşmuyor.
Seri dağılımı: 1 işlem×17, 2×16, 3×4, 4×2, 5×1. %8 tavana BİR kez ulaşılıyor.
Dayanıklılık da kötü: ×2.00'de en iyi 5 işlem çıkarılırsa kâr %67 düşüyor.

**Karar: ikisi de ELENDİ. Config'e dokunulmadı.**
