"""
XAUUSD Veri İndirici — Dukascopy (macOS / Linux / Windows)
==========================================================
`MetaTrader5` Python paketi YALNIZCA Windows'ta çalışır — macOS'ta MT5 yolu
yoktur. Bu modül macOS dahil her platformda çalışır: Dukascopy'nin halka açık
datafeed'inden 1-DAKİKA BID mumlarını indirir (hesap/anahtar gerekmez),
5m/15m/1h/4h'ye toplar ve engine ile uyumlu CSV'lere yazar
(xauusd_5m.csv, xauusd_15m.csv, xauusd_1h.csv, xauusd_4h.csv); istenirse
Excel'e (.xlsx) çevirir.

AVANTAJ: Dukascopy zaman damgaları GMT/UTC'dir → MT5'teki gibi broker saat
dilimi düzeltmesi GEREKMEZ; killzone stratejileriyle doğrudan uyumludur.

Kullanım:
  python3 download_data_dukascopy.py                     # 5 yıl, 5m+15m+1h+4h
  python3 download_data_dukascopy.py --years 2 --excel
  python3 download_data_dukascopy.py --start 2025-01-01 --end 2025-12-31
  python3 download_data_dukascopy.py --intervals 5m,1h

Gereksinim: pip install requests pandas  (Excel için: openpyxl)
"""

from __future__ import annotations

import argparse
import lzma
import struct
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

# Engine ile aynı dosya adları + merge mantığı (tek implementasyon)
from download_data import INTERVAL_FILES, merge_save

BASE_URL = ("https://datafeed.dukascopy.com/datafeed/"
            "{sym}/{y}/{m:02d}/{d:02d}/BID_candles_min_1.bi5")

# .bi5 kayıt formatı (candles_min_1): big-endian
#   uint32 gün başından saniye | uint32 open | uint32 close |
#   uint32 low | uint32 high  | float32 volume
RECORD = struct.Struct(">5If")
DEFAULT_INTERVALS = ["5m", "15m", "1h", "4h"]
PANDAS_FREQ = {"5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h"}


def fetch_day(session: requests.Session, symbol: str,
              day: datetime) -> bytes:
    """Bir günün 1M mum dosyasını indirir. Boş gün (hafta sonu/tatil) → b''."""
    # DİKKAT: Dukascopy URL'lerinde AY 0 TABANLIDIR (Ocak=00)
    url = BASE_URL.format(sym=symbol, y=day.year, m=day.month - 1, d=day.day)
    for attempt in range(4):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 404:
                return b""
            r.raise_for_status()
            return r.content
        except Exception as e:
            wait = 2 ** attempt
            print(f"\n    istek hatası ({attempt+1}/4): {e} — {wait}s bekleniyor")
            time.sleep(wait)
    return b""


def detect_price_scale(raw_prices: list[float]) -> float:
    """Dukascopy fiyatları tamsayı 'point' cinsindendir (XAUUSD'de tipik 1000).
    Böleni otomatik seç: medyan kapanışı makul altın bandına (800–20000$)
    getiren en küçük 10^k."""
    if not raw_prices:
        return 1000.0
    med = sorted(raw_prices)[len(raw_prices) // 2]
    for k in (0, 1, 2, 3, 4, 5):
        d = 10.0 ** k
        if 800.0 <= med / d < 20000.0:
            return d
    return 1000.0


def parse_day(blob: bytes, day: datetime, scale: float | None) -> tuple:
    """LZMA blob → (1M DataFrame, kullanılan scale). Boş blob → (boş df, scale)."""
    if not blob:
        return pd.DataFrame(), scale
    data = lzma.decompress(blob)
    n = len(data) // RECORD.size
    rows = []
    raws = []
    for i in range(n):
        t, o, c, lo, hi, v = RECORD.unpack_from(data, i * RECORD.size)
        rows.append((t, o, hi, lo, c, v))
        raws.append(c)
    if scale is None:
        scale = detect_price_scale([float(x) for x in raws])
    base = pd.Timestamp(day.date())
    idx = base + pd.to_timedelta([r[0] for r in rows], unit="s")
    df = pd.DataFrame({
        "Open":   [r[1] / scale for r in rows],
        "High":   [r[2] / scale for r in rows],
        "Low":    [r[3] / scale for r in rows],
        "Close":  [r[4] / scale for r in rows],
        "Volume": [float(r[5]) for r in rows],
    }, index=idx)
    df.index.name = "Datetime"
    return df, scale


def resample_1m(df_1m: pd.DataFrame, interval: str) -> pd.DataFrame:
    """1M mumları hedef intervale toplar (bar-başlangıcı etiketli; boş
    kovalar — hafta sonu boşlukları — atılır)."""
    freq = PANDAS_FREQ[interval]
    agg = df_1m.resample(freq, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min",
         "Close": "last", "Volume": "sum"})
    return agg.dropna(subset=["Open"])


def download_range(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """[start, end] aralığının 1M mumlarını gün gün indirir (UTC)."""
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (data-downloader)"
    frames = []
    scale = None
    day = datetime(start.year, start.month, start.day)
    total_days = (end - day).days + 1
    empty = 0
    i = 0
    while day <= end:
        i += 1
        blob = fetch_day(session, symbol, day)
        df, scale = parse_day(blob, day, scale)
        if df.empty:
            empty += 1
        else:
            frames.append(df)
        if i % 25 == 0 or day.date() == end.date():
            got = sum(len(f) for f in frames)
            print(f"  [{i}/{total_days}] {day.date()}  "
                  f"toplam {got} × 1M mum  (boş gün: {empty})")
        day += timedelta(days=1)
        time.sleep(0.15)   # nazik hız
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    print(f"  Fiyat böleni: {scale:g}  |  1M mum: {len(out)}  "
          f"({out.index.min()} → {out.index.max()})")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dukascopy'den XAUUSD OHLCV indir — macOS/Linux/Windows, "
                    "hesap gerekmez, zaman damgaları UTC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python3 download_data_dukascopy.py                    # 5 yıl, 5m+15m+1h+4h
  python3 download_data_dukascopy.py --years 2 --excel
  python3 download_data_dukascopy.py --start 2025-06-01 --intervals 5m,1h
        """,
    )
    parser.add_argument("--symbol", default="XAUUSD",
                        help="Dukascopy enstrüman kodu (varsayılan: XAUUSD)")
    parser.add_argument("--years", type=float, default=5.0,
                        help="Kaç YIL geriye (varsayılan: 5)")
    parser.add_argument("--start", default=None,
                        help="Başlangıç YYYY-MM-DD (verilirse --years yok sayılır)")
    parser.add_argument("--end", default=None,
                        help="Bitiş YYYY-MM-DD (varsayılan: bugün)")
    parser.add_argument("--intervals", default=",".join(DEFAULT_INTERVALS),
                        help=f"Virgüllü liste (varsayılan: {','.join(DEFAULT_INTERVALS)})")
    parser.add_argument("--excel", action="store_true",
                        help="CSV'nin yanına .xlsx de yaz")
    args = parser.parse_args()

    intervals = [iv.strip() for iv in args.intervals.split(",") if iv.strip()]
    bad = [iv for iv in intervals if iv not in PANDAS_FREQ]
    if bad:
        print(f"HATA: bilinmeyen interval(ler): {bad} — geçerli: {list(PANDAS_FREQ)}")
        sys.exit(1)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    end_dt = (datetime.strptime(args.end, "%Y-%m-%d") if args.end else now)
    start_dt = (datetime.strptime(args.start, "%Y-%m-%d") if args.start
                else end_dt - timedelta(days=int(args.years * 365)))

    print("\n" + "═" * 62)
    print("  Dukascopy Veri İndirici  (UTC — saat düzeltmesi gerekmez)")
    print(f"  Sembol   : {args.symbol}")
    print(f"  Dönem    : {start_dt.date()} → {end_dt.date()}")
    print(f"  İnterval : {', '.join(intervals)}  (1M'den toplanır)")
    print("═" * 62 + "\n")

    df_1m = download_range(args.symbol, start_dt, end_dt)
    if df_1m.empty:
        print("HATA: hiç veri inmedi (ağ/sembol kontrol edin).")
        sys.exit(1)

    # Kapsama raporu — kısmi indirme sessiz geçilmez
    want = max((end_dt - start_dt).days, 1)
    got = max((df_1m.index.max() - df_1m.index.min()).days, 0)
    print(f"\n  Kapsama: istenen ~{want} gün — gelen {got} gün")
    if df_1m.index.min() > pd.Timestamp(start_dt) + pd.Timedelta(days=5):
        print(f"  ⚠ UYARI: veri {df_1m.index.min().date()}'ten başlıyor "
              f"(istenen {start_dt.date()}).")

    for iv in intervals:
        fname = INTERVAL_FILES.get(iv, f"xauusd_{iv}.csv")
        print(f"\n▶ {iv.upper()}  →  {fname}")
        df = resample_1m(df_1m, iv)
        merge_save(df, fname, iv.upper())
        if args.excel:
            xlsx = fname.replace(".csv", ".xlsx")
            try:
                pd.read_csv(fname, index_col=0, parse_dates=True).to_excel(xlsx)
                print(f"  → {xlsx} kaydedildi (Excel)")
            except Exception as e:
                print(f"  UYARI: Excel yazılamadı ({e}) — pip install openpyxl")

    print("═" * 62)
    print("  Tamamlandı.")
    print("═" * 62)


if __name__ == "__main__":
    main()
