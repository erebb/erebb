# XAUUSD Trading System v10

XAUUSD (altın) için çoklu-strateji backtest motoru + canlı trading botu.
Tüm stratejiler lookahead-bias korumalıdır: sinyal bar kapanışında üretilir,
giriş bir sonraki barın açılışında yapılır.

## İki yapısal kural (5 yıllık analizin çekirdeği)

Sistemin tamamı şu iki kurala dayanır — ikisi de gerçek BingX ücretleriyle
5 yıllık veride IS/OOS ayrımıyla doğrulandı:

1. **`min_stop_pct = 0.6`** — stop mesafesi giriş fiyatının %0.6'sından darsa
   sinyal reddedilir. Gerekçe fiziksel: ücret notional ile, risk stop
   mesafesiyle orantılıdır →
   **`ücret_R ≈ (maker% + taker%) × fiyat / stop_mesafesi`**.
   Ölçüm (861 işlem): stop <%0.2 kovası **net −0.40R/işlem**, stop >%0.6
   kovası **net +0.05R/işlem** — brüt edge her kovada benzer, farkı ücret
   yaratıyor.
2. **`daily_trend_filter` (SMA200)** — sinyal yönü günlük makro trendle
   uyuşmalı; SMA ısınmasında (veri yetersiz) giriş yok. Ana trende karşı
   işlem alınmaz.

Etki (fvg+harmonic, 5 yıl, gerçek maliyet, her işlemde %1 risk):

| | N | PF | IS | OOS | Pozitif yıl |
|---|---|---|---|---|---|
| Filtresiz (eski) | 861 | 0.87 | − | + | 1/6 |
| **İki kuralla** | **167** | **1.51** | **+** | **+** | **5/5** |

Aşırı-uyum değil: stop eşiği **%0.4–1.0 arası her değerde** ve SMA periyodu
**100/150/200/250 hepsinde** IS+OOS pozitif (geniş plato + mekanizma ücret
formülüyle açıklanıyor).

## Stratejiler

5 yıllık IS/OOS elemesinden **ikisi geçti** (config `enabled`); elenenler kodda
kalır ve tek tek seçilerek koşulabilir, ama `hepsi` ve canlı varsayılanına
girmez.

| Strateji | Durum | Tarz | 5 yıl (gerçek maliyet, %1 risk) |
|---|---|---|---|
| `fvg` | ✅ **aktif** | Intraday, none+EMA+blackout+1H swing stop | 111 işlem, **+4.204$**, PF 1.57, DD %6.3 |
| `harmonic` | ✅ **aktif** | 8 harmonik desen PRZ (Gartley/Bat/AltBat/Butterfly/Crab/DeepCrab/Shark/Cypher) | 56 işlem, **+1.157$**, PF 1.32 |
| `threevol` | ❌ elendi | ThreeVol momentum | swing stop'la 51 işlem +430$ ama **IS −264** (OOS'ta değil IS'te çürük) |
| `london` | ❌ elendi | London Reversal | stopları yapısal olarak %0.14 → ücret kapısını hiç geçemiyor (**0 işlem**) |
| `qwe` | ❌ elendi | Fib pullback swing | −628$, PF 0.56, IS ve OOS ikisi de negatif |

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
