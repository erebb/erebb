# XAUUSD Trading System v10

XAUUSD (altın) için çoklu-strateji backtest motoru + canlı trading botu.
Tüm stratejiler lookahead-bias korumalıdır: sinyal bar kapanışında üretilir,
giriş bir sonraki barın açılışında yapılır.

## Stratejiler

| Strateji | Tarz | Sabit preset | 1 yıl dürüst sonuç |
|---|---|---|---|
| `fvg` | Intraday | none + EMA + 1:2fix + blackout 09-11 | 87 işlem, +965, PF 1.35 |
| `threevol` | Intraday | none + EMA + 1:2be + blackout 09-11 | 94 işlem, +2247, PF 1.60 |
| `london` | Intraday | private, immediate, w6 (~06:00) | 6 işlem, +756, PF 8.29 |
| `qwe` | Swing | none, 618 Golden Zone, 15M onay | 59 işlem, +661, PF 1.39 |

İşlem maliyeti modeli config `costs` bölümünden açılır (spread/slippage/komisyon;
varsayılan 0). Uyarı: %0.05 taker + 0.30$ spread ile dar-stoplu fvg/threevol
zarardadır — canlıda düşük ücretli hesap şarttır (bkz. docs/EXIT_ANALYSIS.md).

**Tüm stratejiler SABİT preset'le koşar** (config'ten; en kârlı none
konfigürasyonları, 1 yıllık lookahead'siz grid ile seçildi). GUI parametre
sormaz — strateji + sermaye seçilir, preset işlenir. Manuel bias girme yok.

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
