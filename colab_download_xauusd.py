# -*- coding: utf-8 -*-
"""
XAUUSD 5-YILLIK VERİ İNDİRİCİ — Google Colab (SAĞLAM + DOĞRULAMALI)
==================================================================
Dukascopy halka açık datafeed'inden XAUUSD 1-DAKİKA mumlarını indirir,
5m/15m/1h/4h'ye toplar ve engine ile uyumlu CSV'lere yazar. TEK amaç:
**TradingView'deki fiyatlarla birebir aynı, ÖLÇEĞİ GARANTİLİ DOĞRU** veri.

NEDEN BU SÜRÜM? Otomatik ölçek tahmini bir keresinde fiyatları 10× şişirdi
(altın $3326 yerine $33264 göründü → tüm $-tabanlı strateji eşikleri bozuldu,
backtest çöp oldu). Bu sürüm ölçeği ÜÇ KATLI güvenceyle sabitler ve
sonucu GÖZLE DOĞRULAMANIZ için detaylı grafiklere döker:
  1. XAUUSD için sabit doğru bölen (1000 = 3 ondalık) VARSAYILAN,
  2. sonucu makul altın bandına ($200–$10000) karşı DOĞRULAMA (dışındaysa DURUR),
  3. --price-divisor ile elle geçersiz kılma + seçilen bölenin açık raporu.

GOOGLE COLAB KULLANIMI (tek hücre):
  !pip -q install requests pandas matplotlib mplfinance
  !wget -q <bu dosyanın raw linki> -O colab_download_xauusd.py  # ya da içeriği yapıştır
  %run colab_download_xauusd.py --years 5
Sonunda CSV'ler + zip + detaylı HTML/PNG kalite raporu üretilir; Colab'de
otomatik indirme tetiklenir.

YEREL KULLANIM:
  python3 colab_download_xauusd.py --years 5
  python3 colab_download_xauusd.py --start 2021-01-01 --end 2026-01-01
  python3 colab_download_xauusd.py --price-divisor 1000   # ölçeği elle sabitle

Gereksinim: pip install requests pandas matplotlib  (candlestick için: mplfinance)
"""

from __future__ import annotations

import argparse
import base64
import io
import lzma
import struct
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

try:
    import requests
except ImportError:
    sys.exit("HATA: `pip install requests` gerekli.")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Sabitler ────────────────────────────────────────────────────────────────
BASE_URL = ("https://datafeed.dukascopy.com/datafeed/"
            "{sym}/{y}/{m:02d}/{d:02d}/BID_candles_min_1.bi5")
# .bi5 candles_min_1: big-endian  uint32 sec-of-day | u32 open | u32 close |
#                                 u32 low | u32 high | float32 volume
RECORD = struct.Struct(">5If")
INTERVAL_FILES = {"5m": "xauusd_5m.csv", "15m": "xauusd_15m.csv",
                  "1h": "xauusd_1h.csv", "4h": "xauusd_4h.csv"}
PANDAS_FREQ = {"5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h"}
DEFAULT_INTERVALS = ["5m", "15m", "1h", "4h"]

# XAUUSD için Dukascopy ham tamsayı = fiyat × 1000 (3 ondalık) → doğru bölen 1000.
# (Kanıt: doğru veri $3326.448 = ham 3326448 / 1000.)
XAUUSD_DIVISOR = 1000.0
# Makul altın bandı — sonuç bunun dışındaysa ölçek YANLIŞ demektir → DUR.
GOLD_MIN, GOLD_MAX = 200.0, 10000.0

IN_COLAB = "google.colab" in sys.modules


# ═══════════════════════════════ indirme ════════════════════════════════════

def fetch_day(session: requests.Session, symbol: str, day: datetime) -> bytes:
    """Bir günün 1M dosyası. 404 (hafta sonu/tatil) → b''. 4 deneme, backoff."""
    url = BASE_URL.format(sym=symbol, y=day.year, m=day.month - 1, d=day.day)  # AY 0-TABANLI
    for attempt in range(4):
        try:
            r = session.get(url, timeout=25)
            if r.status_code == 404:
                return b""
            r.raise_for_status()
            return r.content
        except Exception as e:
            wait = 2 ** attempt
            print(f"\n    istek hatası ({attempt+1}/4): {e} — {wait}s bekle")
            time.sleep(wait)
    print(f"\n    ⚠ {day.date()} indirilemedi (4 deneme) — atlanıyor")
    return b""


def parse_day(blob: bytes, day: datetime) -> pd.DataFrame:
    """LZMA blob → HAM (ölçeksiz) 1M DataFrame. Ölçek daha sonra topluca uygulanır."""
    if not blob:
        return pd.DataFrame()
    data = lzma.decompress(blob)
    n = len(data) // RECORD.size
    if n == 0:
        return pd.DataFrame()
    recs = [RECORD.unpack_from(data, i * RECORD.size) for i in range(n)]
    base = pd.Timestamp(day.date())
    idx = base + pd.to_timedelta([r[0] for r in recs], unit="s")
    df = pd.DataFrame({
        "Open":   [r[1] for r in recs], "High": [r[4] for r in recs],
        "Low":    [r[3] for r in recs], "Close": [r[2] for r in recs],
        "Volume": [float(r[5]) for r in recs],
    }, index=idx)
    df.index.name = "Datetime"
    return df


def download_raw(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """[start, end] 1M ham mumları gün gün indirir (UTC, ölçeksiz)."""
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (colab-xauusd-downloader)"
    frames, empty = [], 0
    day = datetime(start.year, start.month, start.day)
    total = (end - day).days + 1
    i = 0
    while day <= end:
        i += 1
        df = parse_day(fetch_day(session, symbol, day), day)
        if df.empty:
            empty += 1
        else:
            frames.append(df)
        if i % 50 == 0 or day.date() >= end.date():
            got = sum(len(f) for f in frames)
            print(f"  [{i}/{total}] {day.date()}  ham 1M: {got:,}  (boş gün: {empty})")
        day += timedelta(days=1)
        time.sleep(0.12)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


# ═══════════════════════════ ölçek + doğrulama ══════════════════════════════

def apply_scale(df_raw: pd.DataFrame, symbol: str,
                override: float | None) -> tuple[pd.DataFrame, float]:
    """Fiyat ölçeğini SABİTLE (10× hatasını önler). Öncelik:
    1) --price-divisor override, 2) XAUUSD ise 1000, 3) medyanı altın bandına
    getiren en küçük 10^k. Sonuç bantta değilse HATA fırlatır (sessiz bozulma yok)."""
    med_raw = float(np.median(df_raw["Close"].values))
    if override is not None:
        div = float(override)
        src = f"elle (--price-divisor {div:g})"
    elif symbol.upper().startswith("XAUUSD"):
        div = XAUUSD_DIVISOR
        src = f"XAUUSD sabiti ({div:g} = 3 ondalık)"
    else:
        div = 1.0
        for k in range(0, 7):
            d = 10.0 ** k
            if GOLD_MIN <= med_raw / d <= GOLD_MAX:
                div = d
                break
        src = f"otomatik (medyanı [{GOLD_MIN:g},{GOLD_MAX:g}] bandına getirir)"

    df = df_raw.copy()
    for c in ("Open", "High", "Low", "Close"):
        df[c] = df[c] / div
    med = float(df["Close"].median())
    print(f"\n  Fiyat böleni : {div:g}   [{src}]")
    print(f"  Medyan kapanış (bölme sonrası): {med:.2f}$")
    if not (GOLD_MIN <= med <= GOLD_MAX):
        raise SystemExit(
            f"\n  ✗ ÖLÇEK HATASI: medyan {med:.1f}$ makul altın bandı "
            f"[{GOLD_MIN:g},{GOLD_MAX:g}] DIŞINDA.\n"
            f"    Ham medyan {med_raw:.0f}. Doğru böleni --price-divisor ile verin "
            f"(altın ~$1500–$4000 olmalı; bölen muhtemelen "
            f"{med_raw/2500:.0f} civarı).")
    return df, div


def validate_integrity(df: pd.DataFrame, name: str) -> list[str]:
    """OHLCV bütünlük denetimi. Bozan hiçbir şey sessiz geçmez."""
    issues = []
    if df.index.duplicated().any():
        issues.append(f"{df.index.duplicated().sum()} yinelenen zaman damgası")
    if not df.index.is_monotonic_increasing:
        issues.append("index artan-sıralı DEĞİL")
    for c in ("Open", "High", "Low", "Close", "Volume"):
        if df[c].isna().any():
            issues.append(f"{c}: {int(df[c].isna().sum())} NaN")
    hi_ok = (df["High"] >= df[["Open", "Close", "Low"]].max(axis=1) - 1e-6)
    lo_ok = (df["Low"] <= df[["Open", "Close", "High"]].min(axis=1) + 1e-6)
    if (~hi_ok).any():
        issues.append(f"{int((~hi_ok).sum())} barda High < max(O,C,L)")
    if (~lo_ok).any():
        issues.append(f"{int((~lo_ok).sum())} barda Low > min(O,C,H)")
    if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
        issues.append("≤0 fiyat var")
    status = "✓ TEMİZ" if not issues else "⚠ SORUN"
    print(f"  [{status}] {name}: {len(df):,} bar  "
          f"{df.index.min()} → {df.index.max()}")
    for it in issues:
        print(f"      - {it}")
    return issues


# ═══════════════════════════════ resample ═══════════════════════════════════

def resample(df_1m: pd.DataFrame, interval: str) -> pd.DataFrame:
    """1M → hedef interval. Bar-AÇILIŞ etiketli (label='left', closed='left') —
    engine bu konvansiyonu bekler. Boş kovalar (hafta sonu) atılır."""
    freq = PANDAS_FREQ[interval]
    agg = df_1m.resample(freq, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min",
         "Close": "last", "Volume": "sum"})
    return agg.dropna(subset=["Open"])


# ═══════════════════════════════ grafikler ══════════════════════════════════

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


def build_charts(df_5m: pd.DataFrame, df_1h: pd.DataFrame,
                 df_1m: pd.DataFrame, symbol: str, out_dir: str) -> str:
    """Detaylı veri-kalite grafikleri → gömülü HTML rapor + PNG'ler.
    TradingView ile GÖZLE karşılaştırma için: fiyat, mum, hacim, kapsama, gap."""
    imgs = []

    # 1) Tüm dönem kapanış (fiyatı TradingView'le karşılaştır)
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(df_1h.index, df_1h["Close"], lw=0.6, color="#c9a227")
    ax.set_title(f"{symbol} — Kapanış (1H, tüm dönem)  |  fiyat aralığı "
                 f"{df_1h['Close'].min():.0f}–{df_1h['Close'].max():.0f}$")
    ax.set_ylabel("Fiyat $")
    ax.grid(alpha=0.25)
    imgs.append(("Tüm dönem fiyat", _b64(fig)))

    # 2) Son 30 gün mum (OHLC gözle sağlaması)
    last = df_1h[df_1h.index >= df_1h.index.max() - pd.Timedelta(days=30)]
    fig, ax = plt.subplots(figsize=(12, 4))
    up = last["Close"] >= last["Open"]
    ax.vlines(last.index, last["Low"], last["High"], color="#888", lw=0.5)
    ax.vlines(last.index[up], last["Open"][up], last["Close"][up],
              color="#26a69a", lw=2)
    ax.vlines(last.index[~up], last["Open"][~up], last["Close"][~up],
              color="#ef5350", lw=2)
    ax.set_title(f"{symbol} — Son 30 gün (1H OHLC çubuk)")
    ax.set_ylabel("Fiyat $")
    ax.grid(alpha=0.25)
    imgs.append(("Son 30 gün mum", _b64(fig)))

    # 3) Hacim (aylık toplam)
    volm = df_5m["Volume"].resample("1ME").sum()
    fig, ax = plt.subplots(figsize=(12, 3))
    ax.bar(volm.index, volm.values, width=20, color="#4C78A8")
    ax.set_title(f"{symbol} — Aylık toplam hacim")
    ax.grid(alpha=0.25)
    imgs.append(("Aylık hacim", _b64(fig)))

    # 4) Kapsama: gün başına 5M bar sayısı (boşluk/eksik tespiti)
    per_day = df_5m.resample("1D").size()
    per_day = per_day[per_day > 0]
    fig, ax = plt.subplots(figsize=(12, 3))
    ax.plot(per_day.index, per_day.values, lw=0.5, color="#54A24B")
    ax.axhline(288, color="#E45756", ls="--", lw=0.8, label="tam gün = 288")
    ax.set_title("Kapsama — gün başına 5M bar (düşükler = eksik/tatil)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)
    imgs.append(("Günlük kapsama", _b64(fig)))

    # 5) Zaman boşlukları (histogram: ardışık 5M barlar arası dakika farkı)
    gaps = df_5m.index.to_series().diff().dt.total_seconds().div(60).dropna()
    big = gaps[gaps > 5]
    fig, ax = plt.subplots(figsize=(12, 3))
    if len(big):
        ax.hist(np.clip(big.values, 0, 4000), bins=60, color="#B279A2")
        ax.set_title(f"5M barlar arası boşluklar (>5dk): {len(big)} adet "
                     f"(çoğu hafta sonu ~2880dk normal)")
    else:
        ax.text(0.5, 0.5, "5dk üstü boşluk yok", ha="center")
    ax.set_xlabel("boşluk (dakika)")
    imgs.append(("Zaman boşlukları", _b64(fig)))

    html = (f'<meta charset="utf-8"><title>{symbol} veri kalite raporu</title>'
            '<style>body{background:#111;color:#ddd;font-family:sans-serif;'
            'max-width:1100px;margin:auto;padding:20px}img{max-width:100%;'
            'border:1px solid #333;margin:6px 0}h2{color:#c9a227}'
            'table{border-collapse:collapse}td,th{border:1px solid #333;'
            'padding:4px 10px;text-align:right}</style>'
            f'<h1>{symbol} — Veri Kalite Raporu</h1>'
            f'<p>Dönem {df_5m.index.min().date()} → {df_5m.index.max().date()} '
            f'| 5M {len(df_5m):,} bar | 1M ham {len(df_1m):,} bar</p>')
    # yıllık aralık tablosu
    html += "<h2>Yıllık fiyat aralığı (TradingView ile karşılaştırın)</h2><table>"
    html += "<tr><th>Yıl</th><th>Min</th><th>Max</th><th>Ort</th><th>5M bar</th></tr>"
    for y, g in df_5m.groupby(df_5m.index.year):
        html += (f"<tr><td>{y}</td><td>{g.Close.min():.0f}</td>"
                 f"<td>{g.Close.max():.0f}</td><td>{g.Close.mean():.0f}</td>"
                 f"<td>{len(g):,}</td></tr>")
    html += "</table>"
    for title, b in imgs:
        html += f"<h2>{title}</h2><img src='data:image/png;base64,{b}'>"
    path = f"{out_dir}/veri_kalite_raporu.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


# ═══════════════════════════════ main ═══════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(
        description="XAUUSD 5-yıllık Dukascopy indirici (Colab, ölçek-garantili)")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--years", type=float, default=5.0)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (verilirse --years yok sayılır)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (varsayılan bugün)")
    ap.add_argument("--intervals", default=",".join(DEFAULT_INTERVALS))
    ap.add_argument("--price-divisor", type=float, default=None,
                    help="Fiyat bölenini ELLE sabitle (XAUUSD için 1000). "
                         "Otomatik tahmine güvenmeyip 10× hatasını kesin önler.")
    ap.add_argument("--out", default=".", help="çıktı dizini")
    args, _ = ap.parse_known_args()   # Colab %run ek argümanlarını yok say

    intervals = [x.strip() for x in args.intervals.split(",") if x.strip()]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else now
    start = (datetime.strptime(args.start, "%Y-%m-%d") if args.start
             else end - timedelta(days=int(args.years * 365)))

    print("═" * 64)
    print("  XAUUSD İNDİRİCİ — Dukascopy (UTC, ölçek-garantili)")
    print(f"  Sembol {args.symbol} | Dönem {start.date()} → {end.date()} "
          f"(~{(end-start).days/365:.1f} yıl)")
    print("═" * 64)

    df_raw = download_raw(args.symbol, start, end)
    if df_raw.empty:
        sys.exit("HATA: hiç veri inmedi (ağ/sembol kontrol edin).")

    df_1m, div = apply_scale(df_raw, args.symbol, args.price_divisor)

    print("\n── Bütünlük denetimi (1M) ──")
    validate_integrity(df_1m, "1M")

    print("\n── Interval'ler ──")
    saved = {}
    total_issues = 0
    for iv in intervals:
        df = resample(df_1m, iv)
        total_issues += len(validate_integrity(df, iv.upper()))
        fname = f"{args.out}/{INTERVAL_FILES.get(iv, f'xauusd_{iv}.csv')}"
        df.to_csv(fname)
        saved[iv] = (fname, df)

    # kapsama uyarısı
    want = max((end - start).days, 1)
    got = (df_1m.index.max() - df_1m.index.min()).days
    print(f"\n  Kapsama: istenen ~{want} gün — gelen {got} gün")
    if got < want - 10:
        print(f"  ⚠ {want-got} gün eksik olabilir (broker tarihçe sınırı?).")

    # detaylı grafikler
    print("\n── Detaylı kalite grafikleri üretiliyor ──")
    df_5m = saved.get("5m", (None, resample(df_1m, "5m")))[1]
    df_1h = saved.get("1h", (None, resample(df_1m, "1h")))[1]
    rep = build_charts(df_5m, df_1h, df_1m, args.symbol, args.out)
    print(f"  Kalite raporu → {rep}")

    # zip + Colab indirme
    import zipfile
    zpath = f"{args.out}/xauusd_5y_veri.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for iv, (fn, _) in saved.items():
            z.write(fn, arcname=fn.split("/")[-1])
        z.write(rep, arcname=rep.split("/")[-1])
    print(f"\n  ZIP → {zpath}")

    print("═" * 64)
    print(f"  BİTTİ. Böl:{div:g} | Bütünlük sorunu: {total_issues} | "
          f"5M {len(df_5m):,} bar")
    print("  Grafiklerdeki fiyatları TradingView XAUUSD ile karşılaştırın —")
    print("  aralık uyuşuyorsa ölçek doğrudur.")
    print("═" * 64)

    if IN_COLAB:
        try:
            from google.colab import files
            files.download(zpath)
        except Exception as e:
            print(f"  (otomatik indirme atlandı: {e} — dosyayı elle indirin)")


if __name__ == "__main__":
    main()
