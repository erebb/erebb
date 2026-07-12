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
