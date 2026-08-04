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
