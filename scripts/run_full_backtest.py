"""
Tam Backtest Koşucusu (GUI paritesi) — çok yıllık veri için
============================================================
Dört stratejinin SABİT preset'lerini (config/default.json) mevcut CSV'ler
üzerinde koşar — GUI'nin `_run_strategy` yolunu AYNEN kullanır (gerçek BingX
maliyetleri, %1 uniform risk, threevol rejim kapısı, limit girişler, swing
stoplar). CSV'lerde kaç yıl varsa onu işler: 5 yıllık veri indirildiyse
(download_data_mt5.py / download_data_dukascopy.py, varsayılan 5 yıl)
5 yıllık backtest olur.

Çıktı: kapsama raporu + strateji tablosu + YIL YIL net PnL kırılımı
(çok yıllık veride hangi yılın taşıdığı / çürüdüğü görülür).

Kullanım:
  python3 scripts/run_full_backtest.py                 # hepsi, 10k kasa
  python3 scripts/run_full_backtest.py --strategy fvg
  python3 scripts/run_full_backtest.py --capital 25000
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sabit preset'lerle tam backtest (GUI paritesi, çok yıllık)")
    parser.add_argument("--strategy", default="hepsi",
                        choices=["hepsi", "fvg", "harmonic", "threevol",
                                 "london", "qwe"])
    parser.add_argument("--capital", type=float, default=10_000.0)
    args = parser.parse_args()

    from gui import _run_strategy, _load_data

    # Kapsama raporu — kaç yıllık veri işlendiği açıkça yazılır
    df_1h, df_5m, bt_start = _load_data()
    days = (df_5m.index.max() - df_5m.index.min()).days
    print("═" * 66)
    print("  TAM BACKTEST — sabit preset'ler, gerçek maliyet, %1 risk")
    print(f"  Veri     : {df_5m.index.min()} → {df_5m.index.max()}"
          f"  ({days} gün ≈ {days/365:.1f} yıl)")
    print(f"  5M/1H bar: {len(df_5m)} / {len(df_1h)}")
    print("═" * 66)

    rows = _run_strategy(args.strategy, capital=args.capital, keep_trades=True)

    print(f"\n{'Strateji':<10}{'Bias':<16}{'N':>5}{'WR%':>7}{'PnL':>12}"
          f"{'PF':>7}{'Sharpe':>8}{'MaxDD%':>8}")
    print("─" * 73)
    total = 0.0
    yearly: dict[str, dict[int, float]] = {}
    for r in rows:
        if r.get("_error"):
            print(f"{r['strategy']:<10}HATA: {r['_error']}")
            continue
        print(f"{r['strategy']:<10}{r['bias']:<16}{r['total']:>5}"
              f"{r['wr']:>7.1f}{r['pnl']:>+12.2f}{r['pf']:>7.2f}"
              f"{r['sharpe']:>8.2f}{r['maxdd']:>8.2f}")
        total += r["pnl"]
        ybuck: dict[int, float] = defaultdict(float)
        for t in r.get("_trades", []):
            if t.exit_time is not None:
                ybuck[t.exit_time.year] += t.pnl_dollar
        yearly[r["strategy"]] = dict(ybuck)
    print("─" * 73)
    print(f"{'TOPLAM':<38}{total:>+12.2f}")

    years = sorted({y for b in yearly.values() for y in b})
    if len(years) > 1:
        print(f"\nYIL YIL NET PnL (maliyet dahil):")
        head = f"{'Strateji':<10}" + "".join(f"{y:>10}" for y in years)
        print(head)
        print("─" * len(head))
        for strat, b in yearly.items():
            print(f"{strat:<10}" + "".join(
                f"{b.get(y, 0.0):>+10.0f}" if y in b else f"{'—':>10}"
                for y in years))
        print("─" * len(head))
        print(f"{'TOPLAM':<10}" + "".join(
            f"{sum(b.get(y, 0.0) for b in yearly.values()):>+10.0f}"
            for y in years))
        print("\nNot: pozisyon boyutu %1×kasa olduğundan yıllar arası bileşik "
              "etkisi PnL'e yansır; yıl sütunları o yıl KAPANAN işlemlerdir.")


if __name__ == "__main__":
    main()
