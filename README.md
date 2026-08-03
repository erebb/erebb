# XAUUSD Trading System v10

XAUUSD (altın) için çoklu-strateji backtest motoru + canlı trading botu.
Tüm stratejiler lookahead-bias korumalıdır: sinyal bar kapanışında üretilir,
giriş bir sonraki barın açılışında yapılır.

## Sistemin çekirdeği (5 yıllık analiz, gerçek BingX ücretleri)

**Ücret modeli — BingX VIP0:** taker **%0.05**, maker **%0.02**, spread 0.30$,
slippage 0.05$/oz. Limit (maker) giriş + taker çıkış ≈ **17.6$/işlem = 0.207R**.
Ücret muhasebesi denetlendi: işlem başına tam 1 kez kesiliyor (111/111) ve elle
hesapla motor **0.0000$ farkla** aynı.

Ücretin R cinsinden büyüklüğü şu ilişkiyle belirlenir — sistemin tasarımı buna
dayanır:

> **`ücret_R ≈ (maker% + taker%) × fiyat / stop_mesafesi`**

Ücret *notional* ile, risk ise *stop mesafesi* ile orantılıdır: dar stop → aynı
%1 risk için dev pozisyon → ücret brüt edge'i yer. Bu yüzden swing-tabanlı geniş
stoplar (mikro stop değil) sistemin ön koşuludur.

**Sistemi taşıyan tek filtre — `daily_trend_filter` (SMA200):** sinyal yönü
günlük makro trendle uyuşmalı; SMA ısınmasında giriş yok. Etkisi (861 işlem,
gerçek ücret): **filtresiz −13.0R (PF 0.98) → trendle +72.1R (PF 1.22)**.
Test edilen her ücret seviyesinde ayakta kaldı; SMA periyodu 100/150/200/250
hepsinde IS+OOS pozitif.

**`min_stop_pct`** (dar-stop reddi) strateji bazında ayarlanır; bu tarifede
fvg/harmonic için gereksiz (maker ucuz), `threevol` %0.1 ile hem daha çok işlem
hem daha çok kâr veriyor (33 → 75 işlem, +10.0R → +12.5R).

### RR: sistemin en pahalı hatasıydı

5 yıllık R dağılımı, TÜM kazananların **tam 2R'de** kesildiğini ve 2.5R+ kovasının
**boş** olduğunu gösterdi — sabit 1:2 hedefi trendleri erken kapatıyordu. Bu ayar
şişik ücret varsayımı döneminde "kesin kâr al" mantığıyla seçilmişti.

| fvg RR | N | R | PF | IS | OOS | Pozitif ay |
|---|---|---|---|---|---|---|
| 1:2 (eski) | 150 | +52.9 | 1.63 | +20.8 | +32.1 | %65 |
| **1:5 (seçilen)** | 121 | **+101.1** | **2.11** | +55.3 | +45.9 | %55 |
| 1:7 (tepe) | 107 | +130.4 | 2.60 | +71.2 | +59.2 | %45 |
| 1:8 | 109 | +105.2 | 2.15 | +51.0 | +54.3 | %40 |

1:8'de düşüp 1:10'da yükselmesi gürültü işareti → güvenilir plato **1:5–1:7**.
**1:5 seçildi**: platonun ortasında (geleceğe karşı en sağlam) ve aylık
tutarlılığı en az bozan nokta.

**Her strateji farklı RR ister** — tek tip RR uygulamak birini bozuyordu:
`fvg`/`harmonic` trend binicisi (1:5), `threevol` momentum scalper'ı (1:2be;
1:3'te IS −2.9 ile çürüyor).

**Denenip REDDEDİLENLER** (hepsi IS/OOS veya kâr testinde kaldı):
- Filtre gevşetme ile işlem artırma: fvg EMA kapalı 317 işlem ama +29.2R
  (kâr yarıya); harmonic EMA kapalı **−7.2R** (zarara geçiyor); blackout kapatma
  her ikisinde de kötü → **filtreler gürültüyü eliyor, az işlem arıza değil**
- Kısmi TP + runner (TP1@1R/1.5R/2R/3R × %30/%50): frontier'ı yenmiyor, her
  varyant kârdan yiyor (en iyisi +79.2R vs düz 1:5'in +101.1R'si)
- BE'li yüksek RR (1:3be/1:4be): 1R'de başabaşa çekmek runner'ları öldürüyor
- threevol'de vol_floor kapatma (IS −3.0) ve swing stop (IS −6.5)

### Sonuç — tek 10.000$ hesap, her işlemde %1 risk, bileşik

**210 işlem (4.2/ay) | WR %35.2 | PF 2.00 | MaxDD %12.3 | IS +73.3R / OOS +61.1R**

| Yıl | İşlem | R | Kasa | Getiri | Kâr |
|---|---|---|---|---|---|
| 2022 | 26 | +19.6 | 12.035$ | +20.4% | +2.035$ |
| 2023 | 31 | +20.6 | 14.631$ | +21.6% | +2.596$ |
| 2024 | 51 | +24.5 | 18.436$ | +26.0% | +3.804$ |
| 2025 | 57 | +48.2 | 29.230$ | +58.5% | +10.794$ |
| 2026 (7 ay) | 45 | +21.6 | **35.991$** | +23.1% | +6.762$ |

Toplam **+%259.9**, yıllık bileşik **+%29.2**, pozitif ay 31/50 (%62),
aylık ortalama +2.69R (medyan +3.04R), **5/5 yıl artıda**.


Karşılaştırma (aynı işlemler, farklı RR):

| Portföy | R | Kasa | Yıllık | MaxDD | Pozitif ay |
|---|---|---|---|---|---|
| A) 1:2 (eski) | +80.4 | 21.610$ | +%16.7 | %22.5 | %65 |
| **B) 1:5 (seçilen)** | **+155.0** | **43.395$** | **+%34.1** | **%19.0** | %62 |
| C) 1:7 | +195.6 | 62.713$ | +%44.4 | %17.7 | %49 |

Dikkate değer: **yüksek RR drawdown'ı DÜŞÜRÜYOR** (%22.5 → %19.0) — büyük
kazançlar düşüşleri hızlı kapatıyor. Ayrıca portföy düzeyinde çeşitlendirme,
yüksek RR'nin tek-strateji bazındaki tutarlılık kaybını telafi ediyor (fvg tek
başına %55 pozitif ay, portföyde %62).

## Stratejiler

5 yıllık IS/OOS elemesinden **üçü geçti** (config `enabled`); elenenler kodda
kalır ve tek tek seçilerek koşulabilir, ama `hepsi` ve canlı varsayılanına
girmez.

| Strateji | Durum | min_stop_pct | 5 yıl (gerçek ücret, %1 risk) |
|---|---|---|---|
| `fvg` | ✅ **aktif** | RR **1:5**, poi_mode=`fvg` — 48 işlem, **+8.151$**, PF 2.87 |
| `harmonic` | ✅ **aktif** | RR **1:5**, poi_mode=`prz` — 69 işlem, **+4.743$**, PF 1.72 |
| `threevol` | ✅ **aktif** | RR **1:2be**, min_stop %0.1 — 75 işlem, **+1.255$**, PF 1.33 |
| `fib` | ✅ **aktif** ⚠ | RR **1:5** — 16 işlem, **+1.950$**, PF 2.59. Sistemin en düşük korelasyonlu stratejisi (0.05–0.19) ama **küçük örneklem** (yılda 3 işlem) → gözlem altında |
| `london` | ❌ elendi | Doğru ayarlarla yeniden test edildi: IS −7.5…−10.0R, PF 0.73–0.75 |
| `qwe` | ❌ elendi | RR/hedef taraması yapıldı: en iyi PF 0.82, `min_rr 2.0`'da IS +4.2 ama OOS −19.6 |

**Tüm stratejiler SABİT preset'le koşar** (config'ten). GUI parametre sormaz —
strateji + sermaye seçilir, preset işlenir. Manuel bias girme yok.

## Dosyalar

- `xauusd_fvg_engine_v10.py` — motor: veri, göstergeler, strateji brain'leri,
  backtest engine'leri, `FibonacciEngine`, `VolumeEngine`, risk yönetimi, analitik.
- `gui.py` — Rich TUI kontrol paneli (backtest çalıştırma): `python3 gui.py`
- `xauusd_live_trader.py` — BingX canlı bot: `python3 xauusd_live_trader.py
  [--strategy fvg|harmonic|threevol|london|qwe] [--dry-run]`. BEŞ strateji de
  canlıda seçilebilir; aktif preset üçü (fvg/harmonic RR 1:5, threevol 1:2be).
  RR, min_stop_pct, SMA200 trend kapısı ve swing stop config'ten okunur →
  **backtest paritesi**. Her işlem eşit risk: kasa × risk_pct (%1).
- `download_data.py` — BingX/Yahoo veri indirici (7/24 kripto-altın).
- `download_data_mt5.py` — MetaTrader 5 indirici (**yalnız Windows** + açık MT5
  terminali): `python download_data_mt5.py` → **5 yıl** 5m/15m/1h/4h CSV (+`--excel`;
  `--years N` ile değiştirilebilir).
  **Broker saati EET ise `--utc-offset 2` (kış) / `3` (yaz) şart** — motor UTC varsayar.
- `download_data_dukascopy.py` — **macOS/Linux/Windows** indirici (hesap gerekmez):
  Dukascopy 1M mumlarından 5m/15m/1h/4h üretir, zaman damgaları doğal UTC:
  `python3 download_data_dukascopy.py [--excel]` (varsayılan **5 yıl**; `--years N`
  ile değiştirilebilir). **Mac kullanıcısı için önerilen yol budur**
  (MetaTrader5 paketi macOS'ta çalışmaz).
- `config/default.json` — tüm strateji/risk/canlı parametreleri (`config.py` yükler).
- `scripts/run_test_matrix.py`, `scripts/test_london_only.py` — hazır backtest matrisleri.
- `scripts/run_full_backtest.py` — sabit preset'lerle tam backtest (GUI paritesi;
  CSV'lerde kaç yıl varsa işler, çok yıllık veride yıl yıl PnL kırılımı yazar).
- `scripts/monthly_charts.py` — **ay ay kapsamlı rapor**: her ay için günlük
  fiyat+EMA+işlem işaretleri, MACD, volatilite (ATR/gerçekleşen/BB), hacim +
  proxy CVD, 5M/15M/1H/4H/1D gösterge tablosu, makro olay notları.
  Çıktı: `reports/monthly/aylik_rapor.html`. (CVD **proxy**'dir — veride bid/ask
  ayrımı yok; haber notları elle derlenmiştir, canlı takvim değildir.)
- `scripts/run_diagnostics_report.py` — **kurumsal teşhis raporu** (motora
  dokunmadan): giriş anı ATR/BBW, long/short asimetri, işlem süresi & zaman-stopu
  what-if, drawdown süresi, haftanın günü, emir doluş/fırsat maliyeti (limit
  yaşam döngüsü 5M'den yeniden kurulur), W taraması, London zaman-toleransı &
  katılık matrisleri, HTF trend uyumu, key-level yakınlığı, kesişim matrisi.
  Çıktı: `reports/diagnostics/rapor_diagnostik.html` + `ledger_diagnostik.csv`.
  `python3 scripts/run_diagnostics_report.py [--fast] [--capital N]`.
- `tests/` — pytest paketi (179 test): `python3 -m pytest tests -q`
- `docs/CODE_AUDIT.md` — kod denetim raporu.

## Hızlı başlangıç

```bash
pip install numpy pandas requests rich pytest   # (yfinance, MetaTrader5, openpyxl opsiyonel)
python3 download_data.py --months 6             # veya Windows'ta download_data_mt5.py
python3 gui.py                                  # backtest menüsü
python3 xauusd_live_trader.py --dry-run         # canlı bot (kağıt işlem)
```

## Önemli notlar

- Mevcut CSV'ler 7/24 kripto-altın verisidir (hafta sonu barları var); stratejilerde
  `weekend_filter` bu yüzden açıktır. MT5 verisiyle çalışırken doğal olarak devre dışı kalır.
- Backtest sonuçları ~4.5 aylık 5M veriyle üretilmiştir — istatistiksel olarak incedir;
  parametre değişikliklerini daha uzun veriyle yeniden doğrulayın.
- Canlı botta `dry_run: true` varsayılandır; gerçek emir için `live_config.json`
  içinde API anahtarları + `--dry-run`'sız çalıştırma gerekir.
