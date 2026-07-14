# -*- coding: utf-8 -*-
"""
XAUUSD İNDİRİCİ — TradingView (OANDA:XAUUSD) — MUM-BİREBİR
==========================================================
Veriyi TradingView'in KENDİ feed'inden (`tvDatafeed`) çeker → grafikte gördüğün
mumların (OHLC) BİREBİR AYNISI. Dukascopy (bid) feed'i farklı broker olduğundan
wick'ler/high-low'lar TradingView'le tutmuyordu; bu araç OANDA:XAUUSD'yi doğrudan
TradingView'den alır, backtest %100 grafikle aynı mumlar üzerinde koşar.

⚠ ÖNEMLİ — GEÇMİŞ BAR SINIRI:
  TradingView küçük zaman dilimlerinde SINIRLI geçmiş verir. Tipik olarak:
    • 1h / 4h / günlük → yıllarca geriye iner (5 yıl genelde tam)
    • 15m → aylar–~1-2 yıl
    • 5m  → haftalar–aylar   (5 YIL 5m ÇOĞU ZAMAN GELMEZ)
  Giriş yapılı (username/password) TradingView hesabı daha derin tarihçe verir.
  Araç HER interval için GERÇEKTE ne indiğini (başlangıç tarihi, bar sayısı,
  istenen dönemin %'si) DÜRÜSTÇE raporlar — sessiz kısmi indirme YOK.

GOOGLE COLAB KULLANIMI:
  !pip -q install --upgrade git+https://github.com/rongardF/tvdatafeed.git pandas matplotlib
  %run colab_download_tradingview.py --years 5
  # daha derin tarihçe için:
  %run colab_download_tradingview.py --years 5 --username KULLANICI --password ŞİFRE

YEREL:
  python3 colab_download_tradingview.py --symbol XAUUSD --exchange OANDA --years 5

Not (TZ): tvDatafeed zaman damgaları UTC varsayılır ve engine UTC bekler.
Grafikte bir barın saatiyle CSV'deki saati karşılaştır; kayma varsa
--utc-offset ile düzelt (örn. feed UTC+3 ise --utc-offset -3).
"""

from __future__ import annotations

import argparse
import base64
import io
import sys
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INTERVAL_FILES = {"5m": "xauusd_5m.csv", "15m": "xauusd_15m.csv",
                  "1h": "xauusd_1h.csv", "4h": "xauusd_4h.csv"}
# gün başına yaklaşık bar (altın ~24s/hafta içi) — n_bars tahmini için
BARS_PER_DAY = {"5m": 288, "15m": 96, "1h": 24, "4h": 6}
IN_COLAB = "google.colab" in sys.modules
GOLD_MIN, GOLD_MAX = 200.0, 10000.0


def _tv_interval(iv: str):
    from tvDatafeed import Interval
    return {"5m": Interval.in_5_minute, "15m": Interval.in_15_minute,
            "1h": Interval.in_1_hour, "4h": Interval.in_4_hour}[iv]


def connect(username: str | None, password: str | None):
    try:
        from tvDatafeed import TvDatafeed
    except ImportError:
        sys.exit("HATA: tvDatafeed yok. Colab'de:\n"
                 "  !pip install --upgrade "
                 "git+https://github.com/rongardF/tvdatafeed.git")
    if username and password:
        print(f"  TradingView girişi: {username}")
        return TvDatafeed(username, password)
    print("  TradingView: anonim (daha sığ tarihçe). Derin veri için "
          "--username/--password verin.")
    return TvDatafeed()


def fetch_interval(tv, symbol: str, exchange: str, iv: str,
                   want_days: float, source_tz: str,
                   utc_offset: float) -> pd.DataFrame:
    """Bir interval'i çeker; istenen günü kapsayacak n_bars ister. TradingView
    ne verirse onu döndürür (dedup+sort, UTC'ye normalize)."""
    need = int(BARS_PER_DAY[iv] * want_days * 1.15) + 500   # payla iste
    need = min(need, 500_000)                               # üst emniyet
    df = None
    for attempt in range(4):
        try:
            df = tv.get_hist(symbol=symbol, exchange=exchange,
                             interval=_tv_interval(iv), n_bars=need)
            break
        except Exception as e:
            wait = 2 ** attempt
            print(f"    {iv} istek hatası ({attempt+1}/4): {e} — {wait}s")
            time.sleep(wait)
    if df is None or len(df) == 0:
        return pd.DataFrame()

    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                            "close": "Close", "volume": "Volume"})
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index.name = "Datetime"
    # TZ normalize → UTC (tvDatafeed genelde UTC döndürür; gerekirse offset)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    if utc_offset:
        df.index = df.index - pd.Timedelta(hours=utc_offset)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def validate_integrity(df: pd.DataFrame, name: str) -> list[str]:
    issues = []
    if df.index.duplicated().any():
        issues.append(f"{int(df.index.duplicated().sum())} yinelenen damga")
    if not df.index.is_monotonic_increasing:
        issues.append("index artan-sıralı değil")
    for c in ("Open", "High", "Low", "Close"):
        if df[c].isna().any():
            issues.append(f"{c}: {int(df[c].isna().sum())} NaN")
    hi_ok = df["High"] >= df[["Open", "Close", "Low"]].max(axis=1) - 1e-6
    lo_ok = df["Low"] <= df[["Open", "Close", "High"]].min(axis=1) + 1e-6
    if (~hi_ok).any():
        issues.append(f"{int((~hi_ok).sum())} barda High<max(O,C,L)")
    if (~lo_ok).any():
        issues.append(f"{int((~lo_ok).sum())} barda Low>min(O,C,H)")
    med = float(df["Close"].median())
    if not (GOLD_MIN <= med <= GOLD_MAX):
        issues.append(f"medyan {med:.0f}$ altın bandı dışında (ölçek/sembol?)")
    print(f"  [{'✓ TEMİZ' if not issues else '⚠ SORUN'}] {name}: "
          f"{len(df):,} bar  {df.index.min()} → {df.index.max()}")
    for it in issues:
        print(f"      - {it}")
    return issues


def coverage(df: pd.DataFrame, iv: str, want_days: float) -> None:
    got_days = (df.index.max() - df.index.min()).days if len(df) else 0
    pct = got_days / want_days * 100 if want_days else 0
    flag = "" if pct >= 90 else "  ⚠ İSTENENDEN AZ"
    print(f"    Kapsama {iv}: {got_days} / ~{int(want_days)} gün "
          f"(%{pct:.0f}){flag}")
    if pct < 90:
        print(f"      → TradingView {iv} feed'i bu kadar geriye vermiyor; "
              f"daha derin tarihçe için --username/--password deneyin ya da "
              f"daha büyük interval kullanın.")


def _b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    if IN_COLAB:
        try:
            from IPython.display import display
            display(fig)
        except Exception:
            pass
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def build_report(saved: dict, symbol: str, exchange: str, out: str) -> str:
    imgs = []
    ref = saved["1h"] if "1h" in saved else next(iter(saved.values()))
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(ref.index, ref["Close"], lw=0.6, color="#c9a227")
    ax.set_title(f"{exchange}:{symbol} — Kapanış  |  "
                 f"{ref['Close'].min():.0f}–{ref['Close'].max():.0f}$")
    ax.grid(alpha=0.25)
    imgs.append(("Tüm dönem fiyat", _b64(fig)))

    last = ref[ref.index >= ref.index.max() - pd.Timedelta(days=20)]
    fig, ax = plt.subplots(figsize=(12, 4))
    up = last["Close"] >= last["Open"]
    ax.vlines(last.index, last["Low"], last["High"], color="#888", lw=0.5)
    ax.vlines(last.index[up], last["Open"][up], last["Close"][up],
              color="#26a69a", lw=2)
    ax.vlines(last.index[~up], last["Open"][~up], last["Close"][~up],
              color="#ef5350", lw=2)
    ax.set_title("Son 20 gün OHLC — bu mumları TradingView ile birebir karşılaştır")
    ax.grid(alpha=0.25)
    imgs.append(("Son 20 gün mum (birebir sağlama)", _b64(fig)))

    if "5m" in saved:
        pd_ = saved["5m"].resample("1D").size()
        pd_ = pd_[pd_ > 0]
        fig, ax = plt.subplots(figsize=(12, 3))
        ax.plot(pd_.index, pd_.values, lw=0.5, color="#54A24B")
        ax.axhline(288, color="#E45756", ls="--", lw=0.8, label="tam gün=288")
        ax.set_title("5M kapsama — gün başına bar")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.25)
        imgs.append(("5M günlük kapsama", _b64(fig)))

    html = (f'<meta charset="utf-8"><title>{exchange}:{symbol} TV veri</title>'
            '<style>body{background:#111;color:#ddd;font-family:sans-serif;'
            'max-width:1100px;margin:auto;padding:20px}img{max-width:100%;'
            'border:1px solid #333;margin:6px 0}h2{color:#c9a227}table{'
            'border-collapse:collapse}td,th{border:1px solid #333;padding:4px 10px;'
            'text-align:right}</style>'
            f'<h1>{exchange}:{symbol} — TradingView feed (mum-birebir)</h1>')
    html += "<h2>Interval kapsaması</h2><table><tr><th>Interval</th><th>Bar</th>"
    html += "<th>Başlangıç</th><th>Bitiş</th></tr>"
    for iv, df in saved.items():
        html += (f"<tr><td>{iv}</td><td>{len(df):,}</td>"
                 f"<td>{df.index.min()}</td><td>{df.index.max()}</td></tr>")
    html += "</table>"
    for t, b in imgs:
        html += f"<h2>{t}</h2><img src='data:image/png;base64,{b}'>"
    path = f"{out}/tv_veri_kalite.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(
        description="XAUUSD TradingView (OANDA) mum-birebir indirici — Colab")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--exchange", default="OANDA")
    ap.add_argument("--years", type=float, default=5.0)
    ap.add_argument("--intervals", default="5m,15m,1h,4h")
    ap.add_argument("--username", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--utc-offset", type=float, default=0.0,
                    help="feed_tz − UTC (saat). Grafikle CSV saati kayıyorsa.")
    ap.add_argument("--source-tz", default="UTC")
    ap.add_argument("--out", default=".")
    args, _ = ap.parse_known_args()

    intervals = [x.strip() for x in args.intervals.split(",") if x.strip()]
    want_days = args.years * 365

    print("═" * 64)
    print(f"  TradingView İNDİRİCİ — {args.exchange}:{args.symbol} (mum-birebir)")
    print(f"  Hedef ~{args.years:g} yıl | interval: {', '.join(intervals)}")
    print("═" * 64)
    tv = connect(args.username, args.password)

    saved, total_issues = {}, 0
    print("\n── İndirme + doğrulama ──")
    for iv in intervals:
        df = fetch_interval(tv, args.symbol, args.exchange, iv, want_days,
                            args.source_tz, args.utc_offset)
        if df.empty:
            print(f"  ✗ {iv}: veri gelmedi (sembol/exchange/erişim kontrol).")
            continue
        total_issues += len(validate_integrity(df, iv.upper()))
        coverage(df, iv, want_days)
        fname = f"{args.out}/{INTERVAL_FILES.get(iv, f'xauusd_{iv}.csv')}"
        df.to_csv(fname)
        saved[iv] = df
        time.sleep(1.0)   # nazik

    if not saved:
        sys.exit("HATA: hiç interval inmedi.")

    # bilinen altın çıpalarıyla gözle sağlama
    print("\n── Bilinen tarih çıpaları (TradingView ile karşılaştır) ──")
    ref = saved["1h"] if "1h" in saved else next(iter(saved.values()))
    for a in ["2024-10-30", "2025-01-02", "2025-07-07", "2026-01-02"]:
        sub = ref[ref.index >= pd.Timestamp(a)]
        if len(sub):
            print(f"  {a}: Close = {sub['Close'].iloc[0]:.1f}$")

    rep = build_report(saved, args.symbol, args.exchange, args.out)
    print(f"\n  Kalite raporu → {rep}")

    import zipfile
    zpath = f"{args.out}/xauusd_tv_veri.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for iv in saved:
            fn = INTERVAL_FILES.get(iv, f"xauusd_{iv}.csv")
            z.write(f"{args.out}/{fn}", arcname=fn)
        z.write(rep, arcname=rep.split("/")[-1])
    print(f"  ZIP → {zpath}")

    print("═" * 64)
    print(f"  BİTTİ. İnen interval: {list(saved)} | bütünlük sorunu: {total_issues}")
    print("  Son-20-gün mum grafiğini TradingView OANDA:XAUUSD ile karşılaştır;")
    print("  mumlar birebir örtüşmeli. Örtüşmüyorsa --utc-offset ile saati hizala.")
    print("═" * 64)

    if IN_COLAB:
        try:
            from google.colab import files
            files.download(zpath)
        except Exception as e:
            print(f"  (otomatik indirme atlandı: {e})")


if __name__ == "__main__":
    main()
