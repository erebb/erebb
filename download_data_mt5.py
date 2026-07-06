"""
XAUUSD Veri İndirici — MetaTrader 5 (MT5)
=========================================
MT5 terminali üzerinden copy_rates_range ile OHLCV indirir; engine ile uyumlu
CSV'lere yazar (xauusd_5m.csv, xauusd_15m.csv, xauusd_1h.csv, xauusd_4h.csv)
ve istenirse Excel'e (.xlsx) çevirir.

GEREKSİNİMLER (yalnızca Windows):
  • MetaTrader 5 terminali kurulu ve AÇIK olmalı (veya --terminal ile yol verin)
  • pip install MetaTrader5 pandas openpyxl

SAAT DİLİMİ UYARISI (önemli):
  Motorun seans/killzone mantığı UTC varsayar. MT5 broker saati genelde
  EET'tir (UTC+2 kış / UTC+3 yaz). Broker'ınız EET ise:
      --utc-offset 2   (kış)   |   --utc-offset 3   (yaz)
  verin; zaman damgalarından bu kadar saat ÇIKARILIR. Emin değilseniz
  broker'ın sunucu saatini MT5'te Market Watch'tan kontrol edin.

Kullanım (Windows'ta):
  python download_data_mt5.py                          # XAUUSD, 1 yıl, 5m+15m+1h+4h
  python download_data_mt5.py --years 2 --excel        # 2 yıl + Excel çıktısı
  python download_data_mt5.py --symbol XAUUSD.a        # broker soneki elle
  python download_data_mt5.py --utc-offset 2           # EET(kış) → UTC
  python download_data_mt5.py --intervals 5m,1h        # yalnız 5m ve 1h
  python download_data_mt5.py --start 2025-01-01 --end 2025-12-31
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

# ── Interval → dosya adı (engine ile aynı adlandırma) ─────────────────────────
INTERVAL_FILES = {
    "5m":  "xauusd_5m.csv",
    "15m": "xauusd_15m.csv",
    "1h":  "xauusd_1h.csv",
    "4h":  "xauusd_4h.csv",
    "1d":  "xauusd_1d.csv",
}
DEFAULT_INTERVALS = ["5m", "15m", "1h", "4h"]

# Broker'ların sık kullandığı XAUUSD sembol varyantları (otomatik arama sırası)
SYMBOL_CANDIDATES = [
    "XAUUSD", "XAUUSD.a", "XAUUSD.r", "XAUUSDm", "XAUUSD.pro",
    "XAUUSD.c", "XAUUSD.i", "GOLD", "GOLD.a", "GOLDmicro",
]

# MT5 sayfa penceresi: copy_rates_range terminaldeki "Max bars in chart"
# ayarıyla sınırlıdır → geniş aralığı AY AY çekmek en güvenlisidir.
CHUNK_DAYS = 30


def _get_mt5():
    """MetaTrader5 modülünü yükler; yoksa/desteklenmiyorsa açıklayıp çıkar."""
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        print("HATA: MetaTrader5 paketi kurulu değil.")
        print("      Bu paket YALNIZCA Windows'ta çalışır ve MT5 terminali gerektirir.")
        print("      Kurulum (Windows): pip install MetaTrader5")
        sys.exit(1)


def _timeframe_map(mt5) -> dict:
    return {
        "1m":  mt5.TIMEFRAME_M1,
        "5m":  mt5.TIMEFRAME_M5,
        "15m": mt5.TIMEFRAME_M15,
        "30m": mt5.TIMEFRAME_M30,
        "1h":  mt5.TIMEFRAME_H1,
        "4h":  mt5.TIMEFRAME_H4,
        "1d":  mt5.TIMEFRAME_D1,
    }


def connect(mt5, terminal_path: str | None, login: int | None,
            password: str | None, server: str | None) -> None:
    """MT5 terminaline bağlanır (terminal AÇIK olmalı)."""
    kwargs = {}
    if terminal_path:
        kwargs["path"] = terminal_path
    if login:
        kwargs.update(login=login, password=password or "", server=server or "")
    if not mt5.initialize(**kwargs):
        code, desc = mt5.last_error()
        print(f"HATA: MT5 bağlantısı kurulamadı: [{code}] {desc}")
        print("      MT5 terminalinin AÇIK olduğundan emin olun.")
        sys.exit(1)
    info = mt5.terminal_info()
    acct = mt5.account_info()
    print(f"  MT5 bağlandı: {getattr(info, 'name', '?')}  "
          f"(build {getattr(info, 'build', '?')})")
    if acct is not None:
        print(f"  Hesap: {acct.login} @ {acct.server}")


def resolve_symbol(mt5, user_symbol: str | None) -> str | None:
    """Sembolü doğrular; verilmediyse bilinen varyantları dener."""
    candidates = ([user_symbol] if user_symbol else []) + SYMBOL_CANDIDATES
    for sym in candidates:
        if sym is None:
            continue
        info = mt5.symbol_info(sym)
        if info is not None:
            if not info.visible and not mt5.symbol_select(sym, True):
                continue   # Market Watch'a eklenemedi
            print(f"  Sembol: {sym} ✓")
            return sym
    # Son çare: terminaldeki tüm sembollerde altın ara
    try:
        allsyms = mt5.symbols_get() or []
        for s in allsyms:
            nm = s.name.upper()
            if "XAU" in nm or "GOLD" in nm:
                if mt5.symbol_select(s.name, True):
                    print(f"  Sembol (otomatik bulundu): {s.name} ✓")
                    return s.name
    except Exception:
        pass
    return None


def rates_to_df(rates, utc_offset_hours: float) -> pd.DataFrame:
    """MT5 rates dizisini engine formatında DataFrame'e çevirir.

    MT5 alanları: time, open, high, low, close, tick_volume, spread,
    real_volume. Volume = real_volume (doluysa) yoksa tick_volume.
    Zaman damgalarından utc_offset_hours ÇIKARILIR (broker saati → UTC)."""
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    idx = pd.to_datetime(df["time"], unit="s")
    if utc_offset_hours:
        idx = idx - pd.Timedelta(hours=utc_offset_hours)
    real = df.get("real_volume")
    use_real = real is not None and float(real.sum()) > 0
    out = pd.DataFrame({
        "Open":   df["open"].astype(float),
        "High":   df["high"].astype(float),
        "Low":    df["low"].astype(float),
        "Close":  df["close"].astype(float),
        "Volume": (real if use_real else df["tick_volume"]).astype(float),
    })
    out.index = idx
    out.index.name = "Datetime"
    return out.sort_index()


def download_interval(mt5, symbol: str, interval: str,
                      start: datetime, end: datetime,
                      utc_offset_hours: float) -> pd.DataFrame:
    """[start, end] aralığını AY AY (CHUNK_DAYS) sayfalayarak indirir.

    copy_rates_range tek çağrıda 'Max bars in chart' sınırına takılabilir;
    dar pencerelerle tüm aralık güvenle toplanır."""
    tf = _timeframe_map(mt5)[interval]
    frames = []
    cursor = start
    page = 0
    while cursor < end:
        page += 1
        win_end = min(cursor + timedelta(days=CHUNK_DAYS), end)
        print(f"  [sayfa {page}] {cursor.date()} → {win_end.date()} ...",
              end=" ", flush=True)
        rates = mt5.copy_rates_range(
            symbol, tf,
            cursor.replace(tzinfo=timezone.utc),
            win_end.replace(tzinfo=timezone.utc),
        )
        df = rates_to_df(rates, utc_offset_hours)
        print(f"{len(df)} mum")
        if not df.empty:
            frames.append(df)
        cursor = win_end
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames)
    return out[~out.index.duplicated(keep="last")].sort_index()


def merge_save(new_df: pd.DataFrame, filepath: str, label: str,
               excel: bool = False) -> None:
    """Yeni veriyi mevcut CSV'ye ekler (dedup + sort); istenirse Excel yazar."""
    if new_df is None or new_df.empty:
        print(f"  UYARI: {label} için veri gelmedi\n")
        return
    try:
        old = pd.read_csv(filepath, index_col=0, parse_dates=True)
        if hasattr(old.index, "tz") and old.index.tz is not None:
            old.index = old.index.tz_localize(None)
        old.index.name = "Datetime"
        before = len(old)
        combined = pd.concat([old, new_df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        print(f"  {label}: {before} eski + {len(combined)-before} yeni = "
              f"{len(combined)} satır  "
              f"({combined.index.min().date()} → {combined.index.max().date()})")
    except FileNotFoundError:
        combined = new_df.sort_index()
        print(f"  {label}: yeni dosya — {len(combined)} satır  "
              f"({combined.index.min().date()} → {combined.index.max().date()})")
    combined.to_csv(filepath, float_format="%.4f")
    print(f"  → {filepath} kaydedildi")
    if excel:
        xlsx = filepath.replace(".csv", ".xlsx")
        try:
            combined.to_excel(xlsx)
            print(f"  → {xlsx} kaydedildi (Excel)")
        except Exception as e:
            print(f"  UYARI: Excel yazılamadı ({e}) — "
                  f"pip install openpyxl gerekebilir")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MetaTrader 5 ile XAUUSD OHLCV indir (Windows + açık MT5 terminali)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python download_data_mt5.py                        # 1 yıl, 5m+15m+1h+4h
  python download_data_mt5.py --years 2 --excel
  python download_data_mt5.py --symbol XAUUSD.a --utc-offset 2
  python download_data_mt5.py --intervals 5m,1h --start 2025-06-01
        """,
    )
    parser.add_argument("--symbol", default=None,
                        help="MT5 sembolü (verilmezse XAUUSD varyantları denenir)")
    parser.add_argument("--years", type=float, default=1.0,
                        help="Kaç YIL geriye (varsayılan: 1)")
    parser.add_argument("--start", default=None, help="Başlangıç YYYY-MM-DD "
                        "(verilirse --years yok sayılır)")
    parser.add_argument("--end", default=None, help="Bitiş YYYY-MM-DD (varsayılan: şimdi)")
    parser.add_argument("--intervals", default=",".join(DEFAULT_INTERVALS),
                        help=f"Virgüllü liste (varsayılan: {','.join(DEFAULT_INTERVALS)})")
    parser.add_argument("--excel", action="store_true",
                        help="CSV'nin yanına .xlsx de yaz")
    parser.add_argument("--utc-offset", type=float, default=0.0,
                        help="Broker saati − UTC farkı (saat). EET broker: kış 2, yaz 3. "
                             "Zaman damgalarından çıkarılır. Varsayılan: 0")
    parser.add_argument("--terminal", default=None,
                        help="terminal64.exe yolu (terminal kapalıysa başlatır)")
    parser.add_argument("--login", type=int, default=None, help="MT5 hesap no (opsiyonel)")
    parser.add_argument("--password", default=None, help="MT5 şifre (opsiyonel)")
    parser.add_argument("--server", default=None, help="MT5 sunucu (opsiyonel)")
    args = parser.parse_args()

    intervals = [iv.strip() for iv in args.intervals.split(",") if iv.strip()]
    bad = [iv for iv in intervals if iv not in INTERVAL_FILES]
    if bad:
        print(f"HATA: bilinmeyen interval(ler): {bad} — "
              f"geçerli: {list(INTERVAL_FILES)}")
        sys.exit(1)

    end_dt = (datetime.strptime(args.end, "%Y-%m-%d")
              if args.end else datetime.utcnow())
    if args.start:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start_dt = end_dt - timedelta(days=int(args.years * 365))

    mt5 = _get_mt5()
    connect(mt5, args.terminal, args.login, args.password, args.server)
    try:
        symbol = resolve_symbol(mt5, args.symbol)
        if not symbol:
            print("HATA: XAUUSD sembolü bulunamadı. --symbol ile broker'ınızın "
                  "sembol adını verin (örn. XAUUSD.a).")
            sys.exit(1)

        print("\n" + "═" * 62)
        print("  MT5 Veri İndirici")
        print(f"  Sembol    : {symbol}")
        print(f"  Dönem     : {start_dt.date()} → {end_dt.date()}")
        print(f"  İnterval  : {', '.join(intervals)}")
        if args.utc_offset:
            print(f"  UTC düzelt: broker − {args.utc_offset:g} saat")
        else:
            print("  UTC düzelt: YOK — broker EET ise --utc-offset 2/3 önerilir!")
        print("═" * 62)

        for iv in intervals:
            fname = INTERVAL_FILES[iv]
            print(f"\n▶ {iv.upper()}  →  {fname}")
            df = download_interval(mt5, symbol, iv, start_dt, end_dt,
                                   args.utc_offset)
            merge_save(df, fname, iv.upper(), excel=args.excel)

        print("═" * 62)
        print("  Tamamlandı.")
        print("═" * 62)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
