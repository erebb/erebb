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
çoğu strateji için gereksiz (maker ucuz), yalnız `threevol` %0.2 gerektiriyor.

### Sonuç — tek 10.000$ hesap, her işlemde %1 risk, bileşik

**265 işlem (53/yıl) | WR %46.0 | PF 1.52 | MaxDD %22.3 | IS +31.1R / OOS +46.9R**

| Yıl | İşlem | R | Kasa sonu | Yıl getirisi |
|---|---|---|---|---|
| 2022 | 34 | +19.8 | 12.141$ | +21.4% |
| 2023 | 50 | −2.3 | 11.808$ | −2.7% |
| 2024 | 57 | +14.2 | 13.515$ | +14.5% |
| 2025 | 81 | +23.7 | 16.982$ | +25.7% |
| 2026 | 43 | +22.5 | **21.167$** | +24.6% |

Toplam **+%111.7**, yıllık bileşik **+%16.2**. 53 ayın 35'i artıda.

## Stratejiler

5 yıllık IS/OOS elemesinden **üçü geçti** (config `enabled`); elenenler kodda
kalır ve tek tek seçilerek koşulabilir, ama `hepsi` ve canlı varsayılanına
girmez.

| Strateji | Durum | min_stop_pct | 5 yıl (gerçek ücret, %1 risk) |
|---|---|---|---|
| `fvg` | ✅ **aktif** | 0.0 | 149 işlem, **+6.628$**, PF 1.63, R +52.9 |
| `harmonic` | ✅ **aktif** | 0.0 | 82 işlem, **+1.514$**, PF 1.27, R +15.0 |
| `threevol` | ✅ **aktif** | 0.2 | 33 işlem, **+1.024$**, PF 1.74, R +10.0 |
| `london` | ❌ elendi | — | 26 işlem, **−768$**, PF 0.73 |
| `qwe` | ❌ elendi | — | IS −3.7R / OOS −14.9R, PF 0.84 |

**Tüm stratejiler SABİT preset'le koşar** (config'ten). GUI parametre sormaz —
strateji + sermaye seçilir, preset işlenir. Manuel bias girme yok.

## Dosyalar

- `xauusd_fvg_engine_v10.py` — motor: veri, göstergeler, strateji brain'leri,
  backtest engine'leri, `FibonacciEngine`, `VolumeEngine`, risk yönetimi, analitik.
- `gui.py` — Rich TUI kontrol paneli (backtest çalıştırma): `python3 gui.py`
- `xauusd_live_trader.py` — BingX canlı bot: `python3 xauusd_live_trader.py
  [--strategy fvg|qwe|threevol|london] [--dry-run]`. DÖRT strateji de canlıda,
  hepsi sabit preset'iyle: fvg/threevol (none+EMA+blackout, threevol'de
  yazılımsal BE@1R), london (private/GARCH otomatik — prompt yok, kısmi TP),
  qwe (none, kısmi TP). Her işlem eşit risk: kasa × risk_pct (%1).
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
