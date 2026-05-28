"""
XAUUSD Veri İndirici  —  yfinance → CSV

Amaç:
  Yahoo Finance 5M veriyi yalnızca son 60 gün için verir. Bu scripti her
  çalıştırdığında yeni veriyi mevcut CSV ile BİRLEŞTİRİR (dedup), böylece
  zamanla 60 günden çok daha uzun 5M geçmişi biriktirebilirsin.

Kullanım:
  python download_data.py
  → xauusd_5m.csv  ve  xauusd_1h.csv  oluşturur/günceller
  → dosyaları GitHub'a yükle, motor bunları otomatik okur

Not:
  - 5M: Yahoo limiti max 60 gün (59 gün çekiyoruz)
  - 1H: Yahoo limiti max 730 gün (120 gün çekiyoruz)
"""

from datetime import datetime, timedelta
import os
import pandas as pd
import yfinance as yf

TICKER   = "GC=F"
FILE_5M  = "xauusd_5m.csv"
FILE_1H  = "xauusd_1h.csv"
DAYS_5M  = 59     # Yahoo 5M sınırı: max 60 gün
DAYS_1H  = 120    # Yahoo 1H sınırı: max 730 gün


def flatten_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df


def normalize_index(df):
    if df is None or df.empty:
        return df
    if hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_convert('UTC').tz_localize(None)
    df.index.name = 'Datetime'
    return df


def download(interval, days):
    end   = datetime.now()
    start = end - timedelta(days=days)
    print(f"  {interval} indiriliyor... ({start.date()} → {end.date()})")
    df = yf.download(TICKER, start=start, end=end,
                     interval=interval, progress=False, auto_adjust=True)
    df = flatten_columns(df)
    df = normalize_index(df)
    keep = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume'] if c in df.columns]
    df = df[keep].dropna(subset=['Close'])
    return df


def merge_save(new_df, filepath, label):
    if new_df is None or new_df.empty:
        print(f"  UYARI: {label} için veri inmedi, atlanıyor")
        return

    if os.path.exists(filepath):
        old = pd.read_csv(filepath, index_col=0, parse_dates=True)
        old = normalize_index(old)
        before = len(old)
        combined = pd.concat([old, new_df])
        # Aynı zaman damgasında yeni veri eskiyi ezsin (~last)
        combined = combined[~combined.index.duplicated(keep='last')]
        combined = combined.sort_index()
        added = len(combined) - before
        print(f"  {label}: {before} eski + {added} yeni = {len(combined)} satır "
              f"({combined.index.min().date()} → {combined.index.max().date()})")
    else:
        combined = new_df.sort_index()
        print(f"  {label}: yeni dosya, {len(combined)} satır "
              f"({combined.index.min().date()} → {combined.index.max().date()})")

    combined.to_csv(filepath, float_format='%.4f')
    print(f"  → {filepath} kaydedildi\n")


def main():
    print("═" * 60)
    print("  XAUUSD Veri İndirici  │  yfinance → CSV")
    print("═" * 60)

    df_5m = download("5m", DAYS_5M)
    merge_save(df_5m, FILE_5M, "5M")

    df_1h = download("1h", DAYS_1H)
    merge_save(df_1h, FILE_1H, "1H")

    print("Tamamlandı. Dosyaları GitHub'a yükleyebilirsin.")


if __name__ == "__main__":
    main()
