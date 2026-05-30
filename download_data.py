"""
XAUUSD Veri İndirici  —  BingX public klines API (kayıt/anahtar gerekmez)

  • Başlangıçta altın sembolünü otomatik bulur (contracts → klines deneme)
  • swap/v3/quote/klines; istek başına 1440 mum; endTime ile GERİYE sayfalanır
  • Her çalıştırmada yeni veriyi mevcut CSV'ye ekler (dedup + sort)
  • Çıktı formatı engine ile uyumlu (Open/High/Low/Close/Volume)

Kullanım:
  python download_data.py --months 6        # son 6 ay, 5m + 1h
  python download_data.py --months 12       # son 12 ay
  python download_data.py --list-symbols    # BingX'teki altın sembollerini göster
  python download_data.py --symbol XAU-USDT --months 6  # sembolü elle gir
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

BASE_URL   = "https://open-api.bingx.com"
KLINES_PATH = "/openApi/swap/v3/quote/klines"  # perpetual OHLCV (CCXT ile aynı)
PAGE_SIZE  = 1440  # BingX istek başına maksimum

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

# Otomatik aramada denenecek bilinen altın sembol adayları.
# DİKKAT: uygulamadaki "GOLD(XAU)-USDT" görünen ad; gerçek API sembolü
# NCCOGOLD2USD-USDT (NCC-O-GOLD). Saf XAUUSD budur, PAXG/XAUT token'dır.
GOLD_CANDIDATES = [
    "NCCOGOLD2USD-USDT",   # = GOLD(XAU)-USDT (saf XAUUSD)
    "GOLD-USDT",
    "XAU-USDT",
    "XAUUSD",
    "PAXG-USDT",
    "XAUT-USDT",
]


# ── Sembol keşif ──────────────────────────────────────────────────────────────

def get_contracts() -> list:
    """BingX tüm perpetual kontrat listesini çeker (public)."""
    try:
        r = requests.get(
            BASE_URL + "/openApi/swap/v2/quote/contracts",
            timeout=15,
        )
        r.raise_for_status()
        body = r.json()
        data = body.get("data", body)
        if isinstance(data, dict):
            data = data.get("data", [])
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"  Contracts çekilemedi: {e}")
        return []


def gold_symbols_from_contracts(rows: list) -> list[dict]:
    """Contracts listesinden altın içeren girişleri döndürür."""
    hits = []
    for c in rows:
        sym  = str(c.get("symbol", ""))
        disp = str(c.get("displayName", ""))
        asset = str(c.get("asset", ""))
        if any(kw in s.upper() for kw in ("XAU", "GOLD", "PAXG", "XAUT")
               for s in (sym, disp, asset)):
            hits.append({
                "symbol":      sym,
                "displayName": disp,
                "asset":       asset,
            })
    return hits


def test_klines(symbol: str) -> bool:
    """Sembolün klines endpoint'ini kabul edip etmediğini kontrol eder."""
    try:
        r = requests.get(
            BASE_URL + KLINES_PATH,
            params={"symbol": symbol, "interval": "1h", "limit": 1},
            timeout=10,
        )
        body = r.json()
        return body.get("code", -1) == 0
    except Exception:
        return False


def resolve_symbol(user_symbol: str | None) -> str | None:
    """
    Kullanılacak sembolü belirler:
    1. Kullanıcı --symbol verdiyse: doğrula, çalışıyorsa kullan.
    2. Contracts listesinden altın sembollerini bul → klines'a dene.
    3. Bilinen adayları dene.
    4. Hiçbiri çalışmıyorsa None döner.
    """
    # 1) Kullanıcı elle verdiyse
    if user_symbol:
        print(f"  Sembol deneniyor: {user_symbol} ...", end=" ", flush=True)
        if test_klines(user_symbol):
            print("✓")
            return user_symbol
        print("✗ (klines endpoint'i kabul etmedi)")

    print("  Altın sembolü otomatik aranıyor...")
    candidates = []

    # 2) Contracts'tan altın sembollerini çek
    rows = get_contracts()
    if rows:
        gold = gold_symbols_from_contracts(rows)
        if gold:
            print(f"  Contracts'ta {len(gold)} altın sembolü bulundu:")
            for g in gold:
                print(f"    {g['symbol']:<28}  ←  {g['displayName']}")
            # ÖNCELİK: uygulamadaki "GOLD(XAU)" (saf XAUUSD) en üste;
            # ardından XAU içerenler; PAXG/XAUT gibi token'lar en sona.
            def rank(g):
                d = g["displayName"].upper()
                if "GOLD(XAU)" in d:        return 0
                if "XAU" in d and "USD" in d: return 1
                if "XAU" in d:              return 2
                return 3
            gold.sort(key=rank)
            candidates = [g["symbol"] for g in gold]

    # 3) Bilinen adayları da ekle (contracts'ta olmayabilir)
    for c in GOLD_CANDIDATES:
        if c not in candidates:
            candidates.append(c)

    # 4) Hepsini klines'a dene
    print("\n  Klines uyumluluğu test ediliyor...")
    for sym in candidates:
        print(f"    {sym:<30}", end=" ", flush=True)
        if test_klines(sym):
            print("✓  BULUNDU")
            return sym
        print("✗")
        time.sleep(0.2)

    return None


# ── API / veri işleme ─────────────────────────────────────────────────────────

def fetch_klines(symbol: str, interval: str, end_ms: int) -> list:
    """
    end_ms'i (endTime) baz alarak GERİYE doğru PAGE_SIZE mum çeker.

    NOT: BingX v3, startTime+endTime+limit birlikte verilince endTime'ı
    baz alıp en yeni 'limit' mumu döndürür (startTime'dan ileri değil).
    Bu yüzden yalnızca endTime gönderip geriye sayfalıyoruz; veri bitince
    (kontrat başlangıcından öncesi) [] gelir.
    """
    params = {
        "symbol":   symbol,
        "interval": interval,
        "endTime":  end_ms,
        "limit":    PAGE_SIZE,
    }
    for attempt in range(4):
        try:
            r = requests.get(
                BASE_URL + KLINES_PATH,
                params=params, timeout=15,
            )
            r.raise_for_status()
            body = r.json()
            if body.get("code", 0) != 0:
                print(f"\n    API hata: {body.get('msg')} — atlıyorum")
                return []
            data = body.get("data", body)
            if isinstance(data, dict):
                data = data.get("data", [])
            return data if isinstance(data, list) else []
        except Exception as e:
            wait = 2 ** attempt
            print(f"\n    İstek hatası ({attempt+1}/4): {e} — {wait}s bekleniyor")
            time.sleep(wait)
    return []


def subtract_months(dt: datetime, months: int) -> datetime:
    import calendar
    month_index = (dt.year * 12 + (dt.month - 1)) - months
    year, month = divmod(month_index, 12)
    month += 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def parse_rows(raw: list) -> pd.DataFrame:
    """
    BingX kline yanıtını DataFrame'e çevirir. İki biçimi de destekler:
      • v3: isimli alanlı nesne  {time, open, high, low, close, volume}
      • v2: pozisyonel dizi       [ts, o, h, l, c, v]
    (alan adları CCXT parseOHLCV'den: timestamp 'time', fallback 'closeTime')
    """
    rows = []
    for row in raw:
        if isinstance(row, dict):
            ts = row.get("time", row.get("closeTime"))
            if ts is None:
                continue
            rows.append({
                "ts":     int(ts),
                "Open":   float(row["open"]),
                "High":   float(row["high"]),
                "Low":    float(row["low"]),
                "Close":  float(row["close"]),
                "Volume": float(row.get("volume", 0)),
            })
        elif isinstance(row, (list, tuple)) and len(row) >= 6:
            rows.append({
                "ts":     int(row[0]),
                "Open":   float(row[1]),
                "High":   float(row[2]),
                "Low":    float(row[3]),
                "Close":  float(row[4]),
                "Volume": float(row[5]),
            })
        else:
            continue
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
    end_ms'ten başlayıp GERİYE doğru sayfalayarak start_ms'e kadar çeker.

    BingX v3 klines endTime'ı baz alıp en yeni PAGE_SIZE mumu döndürür.
    Bu yüzden her sayfanın endTime'ı, bir önceki sayfanın EN ESKİ mumunun
    bir tık öncesidir. Veri start_ms'in altına inince, boş sayfa gelince
    ya da kontrat başlangıcına ulaşınca durur.
    """
    bar_ms    = INTERVAL_MS.get(interval, 300_000)
    cursor    = end_ms             # geriye doğru gerileyen endTime
    frames    = []
    page      = 0
    seen_min  = None               # tekrar/sonsuz döngü koruması

    while cursor >= start_ms:
        page += 1
        c_dt = datetime.utcfromtimestamp(cursor / 1000).strftime("%Y-%m-%d %H:%M")
        print(f"  [sayfa {page}]  ≤ {c_dt} ...", end=" ", flush=True)

        raw = fetch_klines(symbol, interval, cursor)
        df  = parse_rows(raw)
        if df.empty:
            print("boş — kontrat başlangıcına ulaşıldı")
            break

        oldest_ms = int(df.index[0].value // 1_000_000)
        newest_ms = int(df.index[-1].value // 1_000_000)
        o_dt = datetime.utcfromtimestamp(oldest_ms / 1000).strftime("%Y-%m-%d %H:%M")
        print(f"{len(df)} mum  (en eski {o_dt})")

        # Yalnızca start_ms üstündekileri sakla
        keep = df[df.index >= pd.to_datetime(start_ms, unit="ms")]
        if not keep.empty:
            frames.append(keep)

        # En eski mum start_ms'e ulaştıysa bitti
        if oldest_ms <= start_ms:
            break

        # Bu sayfa PAGE_SIZE'dan az mum getirdiyse sona ulaşıldı
        if len(raw) < PAGE_SIZE:
            break

        # İlerleme yoksa dur (aynı en-eski tekrar geldi)
        if seen_min is not None and oldest_ms >= seen_min:
            print("  İlerleme durdu — bitiriliyor.")
            break
        seen_min = oldest_ms

        cursor = oldest_ms - bar_ms    # bir önceki muma geç
        time.sleep(0.15)

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def merge_save(new_df: pd.DataFrame, filepath: str, label: str) -> None:
    if new_df is None or new_df.empty:
        print(f"  UYARI: {label} için veri gelmedi\n")
        return

    try:
        old = pd.read_csv(filepath, index_col=0, parse_dates=True)
        if hasattr(old.index, "tz") and old.index.tz is not None:
            old.index = old.index.tz_localize(None)
        old.index.name = "Datetime"
        before   = len(old)
        combined = pd.concat([old, new_df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        added    = len(combined) - before
        print(f"  {label}: {before} eski + {added} yeni = {len(combined)} satır  "
              f"({combined.index.min().date()} → {combined.index.max().date()})")
    except FileNotFoundError:
        combined = new_df.sort_index()
        print(f"  {label}: yeni dosya — {len(combined)} satır  "
              f"({combined.index.min().date()} → {combined.index.max().date()})")

    combined.to_csv(filepath, float_format="%.4f")
    print(f"  → {filepath} kaydedildi\n")


# ── Ana program ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BingX public API ile OHLCV veri indir (kayıt gerekmez)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python download_data.py --months 6          # son 6 ay, 5m + 1h (otomatik sembol)
  python download_data.py --months 12         # son 12 ay
  python download_data.py --list-symbols      # BingX'teki altın sembollerini listele
  python download_data.py --symbol XAU-USDT --months 6   # sembolü elle belirt
        """,
    )
    parser.add_argument(
        "--symbol", default=None,
        help="BingX API sembolü (belirtilmezse otomatik aranır)",
    )
    parser.add_argument(
        "--list-symbols", action="store_true",
        help="BingX'teki altın sembollerini listele ve çık",
    )
    parser.add_argument(
        "--interval", default=None,
        help="Tek interval: 1m 5m 15m 1h 4h 1d  (varsayılan: 5m + 1h)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="5m + 15m + 1h + 4h + 1d hepsini indir",
    )
    parser.add_argument(
        "--months", type=int, default=None,
        help="Kaç AY geriye gidilsin (örn. 6)",
    )
    parser.add_argument(
        "--days", type=int, default=90,
        help="Kaç GÜN geriye gidilsin (varsayılan: 90)",
    )
    parser.add_argument(
        "--start", default=None,
        help="Başlangıç tarihi YYYY-MM-DD",
    )
    args = parser.parse_args()

    # ── Sembol listele ve çık ─────────────────────────────────────────────────
    if args.list_symbols:
        print("BingX altın kontratları aranıyor...\n")
        rows = get_contracts()
        gold = gold_symbols_from_contracts(rows)
        if not gold:
            print("  Altın sembolü bulunamadı (ağ sorunu olabilir).")
            return
        print(f"{'API symbol':<30}  {'displayName':<25}  {'asset'}")
        print("─" * 70)
        for g in gold:
            print(f"  {g['symbol']:<28}  {g['displayName']:<25}  {g['asset']}")
        print("\nKlines uyumluluğu test ediliyor...")
        for g in gold:
            ok = test_klines(g["symbol"])
            print(f"  {g['symbol']:<30}  {'✓ klines OK' if ok else '✗ klines KABUL ETMİYOR'}")
            time.sleep(0.2)
        return

    # ── Sembol belirle ────────────────────────────────────────────────────────
    symbol = resolve_symbol(args.symbol)
    if not symbol:
        print("\n  HATA: Çalışan altın sembolü bulunamadı.")
        print("  Öneri: python download_data.py --list-symbols")
        return

    # ── Tarih aralığı ─────────────────────────────────────────────────────────
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

    print("\n" + "═" * 62)
    print("  BingX Veri İndirici")
    print(f"  Sembol   : {symbol}")
    print(f"  Dönem    : {start_dt.date()} → {end_dt.date()}")
    print(f"  İnterval : {', '.join(intervals)}")
    print("═" * 62)

    for iv in intervals:
        fname = INTERVAL_FILES.get(iv, f"xauusd_{iv}.csv")
        print(f"\n▶ {iv.upper()}  →  {fname}")
        df = download_range(symbol, iv, start_ms, end_ms)
        merge_save(df, fname, iv.upper())

    print("═" * 62)
    print("  Tamamlandı.")
    print("═" * 62)


if __name__ == "__main__":
    main()
