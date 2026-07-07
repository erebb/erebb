# XAUUSD Trading System v10

XAUUSD (altın) için çoklu-strateji backtest motoru + canlı trading botu.
Tüm stratejiler lookahead-bias korumalıdır: sinyal bar kapanışında üretilir,
giriş bir sonraki barın açılışında yapılır.

## Stratejiler

| Strateji | Tarz | Bias | Özet |
|---|---|---|---|
| `fvg` | Intraday | seçilir | 1H FVG + 5M MSB konfluensi (+OB/PRZ/harmonik) |
| `threevol` | Intraday | seçilir | Three Vol Directional (hacimli MSB) |
| `london` | Intraday | **private (sabit)** | ICT Judas Swing: Asya/PDH-PDL süpürme → retest girişi, kısmi TP |
| `qwe` | Swing | **none (sabit)** | Fib pullback: 1H BOS+HH → %61.8 Golden Zone, 15M onay, 4H yön, kısmi TP |

Sabit-bias stratejilerin (london/qwe) preset'leri grid backtest ile doğrulanmıştır
ve GUI'de bias/TBE seçimi bunlara uygulanmaz.

## Dosyalar

- `xauusd_fvg_engine_v10.py` — motor: veri, göstergeler, strateji brain'leri,
  backtest engine'leri, `FibonacciEngine`, `VolumeEngine`, risk yönetimi, analitik.
- `gui.py` — Rich TUI kontrol paneli (backtest çalıştırma): `python3 gui.py`
- `xauusd_live_trader.py` — BingX canlı bot: `python3 xauusd_live_trader.py
  [--strategy fvg|qwe] [--dry-run]`. QWE seçilirse bias zorunlu none, kısmi TP
  iki yarım emirle + yazılımsal breakeven.
- `download_data.py` — BingX/Yahoo veri indirici (7/24 kripto-altın).
- `download_data_mt5.py` — MetaTrader 5 indirici (**yalnız Windows** + açık MT5
  terminali): `python download_data_mt5.py --years 1` → 5m/15m/1h/4h CSV (+`--excel`).
  **Broker saati EET ise `--utc-offset 2` (kış) / `3` (yaz) şart** — motor UTC varsayar.
- `download_data_dukascopy.py` — **macOS/Linux/Windows** indirici (hesap gerekmez):
  Dukascopy 1M mumlarından 5m/15m/1h/4h üretir, zaman damgaları doğal UTC:
  `python3 download_data_dukascopy.py --years 1 [--excel]`. **Mac kullanıcısı için
  önerilen yol budur** (MetaTrader5 paketi macOS'ta çalışmaz).
- `config/default.json` — tüm strateji/risk/canlı parametreleri (`config.py` yükler).
- `scripts/run_test_matrix.py`, `scripts/test_london_only.py` — hazır backtest matrisleri.
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
