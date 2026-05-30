"""
XAUUSD Veri İndirici  —  BingX public klines API (kayıt/anahtar gerekmez)

  • İstek başına 1440 mum; startTime/endTime döngüsüyle sayfalanır
  • Her çalıştırmada yeni veriyi mevcut CSV'ye ekler (dedup + sort)
  • Çıktı formatı LiveDataEngine / engine ile uyumlu (Open/High/Low/Close/Volume)

Kullanım:
  python download_data.py                         # varsayılan: 5m + 1h, son 90 gün
  python download_data.py --months 6              # son 6 ay, 5m + 1h
  python download_data.py --days 365              # son 365 gün
  python download_data.py --start 2024-01-01      # belirli başlangıç
  python download_data.py --interval 5m           # yalnızca 5m
  python download_data.py --symbol NCCGOLD2USD-USDT --interval 1h --months 24
"""

import argparse
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

BASE_URL  = "https://open-api.bingx.com"
PAGE_SIZE = 1440  # BingX istek başına maksimum

INTERVAL_FILES = {
    "5m":  "xauusd_5m.csv",
    "15m": "xauusd_15m.csv",
    "1h":  "xauusd_1h.csv",
    "4h":  "xauusd_4h.csv",
    "1d":  "xauusd_1d.csv",
}

INTERVAL_MS = {
    "1m":  60_000,
    "3m":  180_000,
    "5m":  300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h":  3_600_000,
    "2h":  7_200_000,
    "4h":  14_400_000,
    "6h":  21_600_000,
    "12h": 43_200_000,
    "1d":  86_400_000,
    "1w":  604_800_000,
}


def fetch_page(symbol: str, interval: str,
               start_ms: int, end_ms: int) -> list[dict]:
    """Tek sayfa kline verisi çeker; liste boşsa [] döner."""
    params = {
        "symbol":    symbol,
        "interval":  interval,
        "startTime": start_ms,
        "endTime":   end_ms,
        "limit":     PAGE_SIZE,
    }
    for attempt in range(4):
        try:
            r = requests.get(
                BASE_URL + "/openApi/swap/v2/quote/klines",
                params=params, timeout=15,
            )
            r.raise_for_status()
            body = r.json()
            if body.get("code", 0) != 0:
                print(f"    API hata: {body.get('msg')} — atlıyorum")
                return []
            data = body.get("data", body)
            if isinstance(data, dict):
                data = data.get("data", [])
            return data if isinstance(data, list) else []
        except Exception as e:
            wait = 2 ** attempt
            print(f"    İstek hatası ({attempt+1}/4): {e} — {wait}s bekleniyor")
            time.sleep(wait)
    return []


def subtract_months(dt: datetime, months: int) -> datetime:
    """dt tarihinden takvim-doğru olarak 'months' ay çıkarır."""
    import calendar
    month_index = (dt.year * 12 + (dt.month - 1)) - months
    year, month = divmod(month_index, 12)
    month += 1
    # Ay sonu taşmasını önle (örn. 31 → 28/30)
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def parse_rows(raw: list) -> pd.DataFrame:
    """[[ts, o, h, l, c, v], ...] → DataFrame[Open,High,Low,Close,Volume]"""
    rows = []
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        rows.append({
            "ts":     int(row[0]),
            "Open":   float(row[1]),
            "High":   float(row[2]),
            "Low":    float(row[3]),
            "Close":  float(row[4]),
            "Volume": float(row[5]),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
    df.index = df.index.tz_localize(None)
    df.index.name = "Datetime"
    return df.sort_index()


def download_range(symbol: str, interval: str,
                   start_ms: int, end_ms: int) -> pd.DataFrame:
    """
    start_ms → end_ms arasını PAGE_SIZE'lık sayfalara bölerek çeker.
    İlerlemeyi satır satır basar.
    """
    step   = INTERVAL_MS.get(interval, 300_000) * PAGE_SIZE
    cursor = start_ms
    frames = []
    total  = max(1, (end_ms - start_ms) // step + 1)
    page   = 0

    while cursor < end_ms:
        page_end = min(cursor + step, end_ms)
        page += 1
        start_dt = datetime.utcfromtimestamp(cursor / 1000).strftime("%Y-%m-%d %H:%M")
        end_dt   = datetime.utcfromtimestamp(page_end / 1000).strftime("%Y-%m-%d %H:%M")
        print(f"  [{page}/{total}]  {start_dt}  →  {end_dt} ...", end=" ", flush=True)

        raw = fetch_page(symbol, interval, cursor, page_end)
        if raw:
            df = parse_rows(raw)
            frames.append(df)
            print(f"{len(df)} mum")
        else:
            print("boş")

        cursor = page_end + 1
        time.sleep(0.15)  # rate-limit'e saygı

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def merge_save(new_df: pd.DataFrame, filepath: str, label: str) -> None:
    """Yeni veriyi mevcut CSV ile birleştirir (dedup), kaydeder."""
    if new_df is None or new_df.empty:
        print(f"  UYARI: {label} için veri gelmedi, atlanıyor\n")
        return

    try:
        old = pd.read_csv(filepath, index_col=0, parse_dates=True)
        if hasattr(old.index, "tz") and old.index.tz is not None:
            old.index = old.index.tz_localize(None)
        old.index.name = "Datetime"
        before = len(old)
        combined = pd.concat([old, new_df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        added = len(combined) - before
        print(f"  {label}: {before} eski + {added} yeni = {len(combined)} satır  "
              f"({combined.index.min().date()} → {combined.index.max().date()})")
    except FileNotFoundError:
        combined = new_df.sort_index()
        print(f"  {label}: yeni dosya — {len(combined)} satır  "
              f"({combined.index.min().date()} → {combined.index.max().date()})")

    combined.to_csv(filepath, float_format="%.4f")
    print(f"  → {filepath} kaydedildi\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BingX public API ile OHLCV veri indir (kayıt gerekmez)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python download_data.py                              # 5m + 1h, son 90 gün
  python download_data.py --months 6                   # 5m + 1h, son 6 AY
  python download_data.py --months 12                  # 5m + 1h, son 12 ay
  python download_data.py --days 365                   # son 1 yıl
  python download_data.py --start 2024-01-01           # belirli başlangıç
  python download_data.py --interval 5m --days 180     # yalnızca 5m, 6 ay
  python download_data.py --interval 1h --days 730     # yalnızca 1h, 2 yıl
  python download_data.py --all                        # 5m+15m+1h+4h+1d
        """,
    )
    parser.add_argument(
        "--symbol", default="NCCGOLD2USD-USDT",
        help="BingX sembolü (varsayılan: NCCGOLD2USD-USDT = GOLD(XAU)-USDT)",
    )
    parser.add_argument(
        "--interval", default=None,
        help="Tek interval: 1m 3m 5m 15m 30m 1h 2h 4h 6h 12h 1d 1w "
             "(varsayılan: 5m + 1h)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="5m + 15m + 1h + 4h + 1d hepsini indir",
    )
    parser.add_argument(
        "--months", type=int, default=None,
        help="Kaç AY geriye gidilsin (örn. 6 = son 6 ay). --days'i geçersiz kılar",
    )
    parser.add_argument(
        "--days", type=int, default=90,
        help="Kaç gün geriye gidilsin (varsayılan: 90)",
    )
    parser.add_argument(
        "--start", default=None,
        help="Başlangıç tarihi: YYYY-MM-DD  (--days'i geçersiz kılar)",
    )
    args = parser.parse_args()

    if args.start:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    elif args.months:
        start_dt = subtract_months(datetime.utcnow(), args.months)
    else:
        start_dt = datetime.utcnow() - timedelta(days=args.days)

    end_dt   = datetime.utcnow()
    start_ms = int(start_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms   = int(end_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

    if args.all:
        intervals = ["5m", "15m", "1h", "4h", "1d"]
    elif args.interval:
        intervals = [args.interval]
    else:
        intervals = ["5m", "1h"]

    print("═" * 62)
    print("  BingX Veri İndirici  (kayıtsız / public API)")
    print(f"  Sembol   : {args.symbol}")
    print(f"  Dönem    : {start_dt.date()} → {end_dt.date()}")
    print(f"  İnterval : {', '.join(intervals)}")
    print("═" * 62)

    for iv in intervals:
        fname = INTERVAL_FILES.get(iv, f"xauusd_{iv}.csv")
        print(f"\n▶ {iv.upper()}  →  {fname}")
        df = download_range(args.symbol, iv, start_ms, end_ms)
        merge_save(df, fname, iv.upper())

    print("═" * 62)
    print("  Tamamlandı.")
    print("═" * 62)


if __name__ == "__main__":
    main()
