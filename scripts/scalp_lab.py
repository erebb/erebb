# -*- coding: utf-8 -*-
"""
SCALP LABORATUVARI — prop firm (MT5) için kısa vadeli varyant testi
====================================================================
TEST AMAÇLIDIR. Motor/gui/config diske YAZILMAZ; kaynak bellekte yamanır,
config bellekte değiştirilip her koşudan sonra eski hâline döndürülür.

NEDEN BU TEST ANLAMLI
---------------------
Sistemin tasarımını belirleyen denklem:  ücret_R ≈ ücret% × fiyat / stop
Dar stop → ücret R cinsinden patlar. BingX VIP0'da gidiş-dönüş komisyon
notional'ın %0.07'si; 5$'lık scalp stopunda bu 1R kazancın %43.8'ini yer —
scalp orada YAPISAL OLARAK imkânsız.

MT5/prop firm maliyeti farklıdır: komisyon lot başına SABİT ($3–7/lot/yön),
yani $3.5/lot'ta notional'ın yalnızca %0.0026'sı — BingX'ten ~27 kat ucuz.
Aynı 5$ stopta ücret 1R'nin %5.4'ü. Yani scalp BingX'te ölür, MT5'te
yaşayabilir. Bu laboratuvar iki maliyet profilini de koşar.

DEĞİŞTİRİLEN KALDIRAÇLAR
------------------------
  swing_stop=False  → stop 1H swing yerine POI yapısından, DAHA DAR
  rr                → 1:5 yerine 1:1.5 / 1:2 / 1:3 (daha hızlı TP)
  time_exit_bars    → N bar sonra market'ten kapat (5M bar; 24=2s, 48=4s)
                      gui'de sabit None; bellekte yamanır

ÖLÇÜM
-----
Bakiye/düşüş OLAY TABANLI (scripts/equity.py). Ayrıca prop firm bakışı:
yüzen zarar dahil düşüş ve %10 limitte kullanılabilecek risk oranı.

Kullanım: python3 scripts/scalp_lab.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

GUI_SRC = ROOT / "gui.py"
SPLIT = pd.Timestamp("2025-01-11")
STRATS = ["fvg", "harmonic", "threevol", "fib"]
BASE_TOP = 134.4

# ── maliyet profilleri ──────────────────────────────────────────────────
# commission_pct/maker_pct: TEK YÖN, notional yüzdesi.
COSTS = {
    "BingX VIP0": dict(spread_usd=0.30, slippage_usd=0.05,
                       commission_pct=0.05, maker_pct=0.02),
    # $3.5/lot/yön = $0.035/oz ≈ altın 2700$'da notional'ın %0.0013'ü
    "MT5 prop":   dict(spread_usd=0.20, slippage_usd=0.05,
                       commission_pct=0.0013, maker_pct=0.0013),
    # STRES: kötü senaryo — geniş spread, $7/lot komisyon, 3x slippage.
    # Scalp'te maliyet varsayımı sonucu belirler; kırılganlığı ölçmek şart.
    "MT5 kotu":   dict(spread_usd=0.45, slippage_usd=0.15,
                       commission_pct=0.0026, maker_pct=0.0026),
}

# ── denenecek konfigürasyonlar ──────────────────────────────────────────
# (etiket, swing_stop, rr, time_exit_bars)  teb=None → zaman çıkışı yok
VARIANTS = [
    ("mevcut (config)",     None,  None,     None),
    ("scalp A  dar 1:2",    False, "1:2fix", None),
    ("scalp B  dar 1:2 +4s", False, "1:2fix", 48),
    ("scalp C  dar 1:3 +8s", False, "1:3fix", 96),
    ("scalp D  dar 1:1.5",  False, "1:1.5",  24),
]

_ANCHOR = "time_exit_bars=None, ema_macd_filter=p[\"emf\"],"


def load_gui(teb):
    """gui.py'yi bellekte yamalayıp 'gui' olarak yükle (disk değişmez)."""
    src = GUI_SRC.read_text(encoding="utf-8")
    n = src.count(_ANCHOR)
    if n < 4:
        raise SystemExit("çıpa %d kez bulundu — gui.py değişmiş, "
                         "scripts/scalp_lab.py güncellenmeli" % n)
    src = src.replace(_ANCHOR,
                      "time_exit_bars=_LAB_TEB, ema_macd_filter=p[\"emf\"],")
    sys.modules.pop("gui", None)
    mod = types.ModuleType("gui")
    mod.__file__ = str(GUI_SRC)
    # Değişkeni kaynağa EKLEMEK yerine modül sözlüğüne önceden koy:
    # `from __future__ import annotations` dosyanın ilk deyimi olmak zorunda,
    # başa satır eklemek SyntaxError verir.
    mod.__dict__["_LAB_TEB"] = teb
    sys.modules["gui"] = mod
    exec(compile(src, str(GUI_SRC), "exec"), mod.__dict__)
    return mod


def run(swing: bool, rr: str, teb, cost: dict) -> pd.DataFrame:
    from config import get_config
    cfg = get_config()
    # swing/rr None → config'e DOKUNMA. Referans koşu gerçek preset'lerle
    # koşmalı: threevol swing_stop=False + rr=1:2be, diğerleri True + 1:5fix.
    # (İlk sürüm hepsine swing_stop=True veriyordu → referans GERÇEK sistemi
    #  üretmiyordu: N=180 yerine 210, DD %18.4 yerine %12.3.)
    keep = {}
    for s in STRATS:
        keep[s] = (cfg.get(s, "swing_stop", default=True),
                   cfg.get(s, "rr", default="1:5fix"),
                   cfg.get(s, "min_stop_pct", default=0.0))
        if swing is not None:
            cfg.set(s, "swing_stop", swing)
        if rr is not None:
            cfg.set(s, "rr", rr)
        if swing is False:
            cfg.set(s, "min_stop_pct", 0.0)   # scalp'te dar stop reddi kapalı
    kc = {k: cfg.get("costs", k, default=0) for k in cost}
    for k, v in cost.items():
        cfg.set("costs", k, v)
    try:
        gui = load_gui(teb)
        rows = []
        for s in STRATS:
            r = gui._run_strategy(s, keep_trades=True)[0]
            for t in r.get("_trades", []):
                if t.exit_time is None or t.risk_dollar <= 0:
                    continue
                e = pd.Timestamp(str(t.signal.entry_time)[:19])
                x = pd.Timestamp(str(t.exit_time)[:19])
                rows.append(dict(s=s, entry=e, exit=x,
                                 r=t.pnl_dollar / t.risk_dollar,
                                 px=t.entry_price, sl=t.sl,
                                 stop=t.risk, mae=getattr(t, "mae_r", np.nan),
                                 dur_h=(x - e).total_seconds() / 3600,
                                 reason=getattr(t, "exit_reason", "")))
    finally:
        for s in STRATS:
            cfg.set(s, "swing_stop", keep[s][0])
            cfg.set(s, "rr", keep[s][1])
            cfg.set(s, "min_stop_pct", keep[s][2])
        for k, v in kc.items():
            cfg.set("costs", k, v)
    return pd.DataFrame(rows).sort_values("exit").reset_index(drop=True)


def slug(x: str) -> str:
    """Dosya adı için güvenli etiket."""
    out = x.lower()
    for ch in " ()+.:":
        out = out.replace(ch, "_")
    return "_".join(t for t in out.split("_") if t)


def float_dd(d: pd.DataFrame, f: float) -> float:
    """Yüzen zarar dahil maks. düşüş — prop firmalar anlık özkaynak ölçer.
    Açık pozisyonların MAE'si kadar yüzen zarar varsayılır (üst sınır)."""
    ev = []
    for i, r in enumerate(d.itertuples()):
        ev.append((r.entry, 0, i))
        ev.append((getattr(r, "exit"), 1, i))
    ev.sort(key=lambda t: (t[0], t[1]))
    bal, risk, op, pts = 10000.0, {}, set(), []
    for t, k, i in ev:
        if k == 0:
            risk[i] = f * bal
            op.add(i)
        else:
            bal += risk.pop(i, 0.0) * float(d.r.iloc[i])
            op.discard(i)
        fl = sum(risk.get(j, 0.0) * -(d.mae.iloc[j] if d.mae.notna().iloc[j]
                                      else 0.0) for j in op)
        pts.append(bal + fl)
    c = pd.Series(pts)
    return float(abs((c / c.cummax() - 1).min()) * 100)


def risk_for_prop(d: pd.DataFrame, limit: float = 10.0,
                  buffer: float = 0.8) -> float:
    """Yüzen dahil düşüşü limit×buffer'a getiren risk oranı."""
    lo, hi = 0.0003, 0.02
    for _ in range(35):
        mid = (lo + hi) / 2
        if float_dd(d, mid) > limit * buffer:
            hi = mid
        else:
            lo = mid
    return lo


def report(label: str, cost_name: str, d: pd.DataFrame) -> None:
    from equity import event_equity
    if d.empty:
        print("  %-22s %-11s  ISLEM YOK" % (label, cost_name))
        return
    isk = d.entry < SPLIT
    e = event_equity(d, 0.01)
    fp = risk_for_prop(d)
    ep = event_equity(d, fp)
    print("  %-22s %-11s N=%4d WR=%4.1f%% R=%+7.1f (IS%+6.1f/OOS%+6.1f) "
          "sure=%5.1fs stop=%5.1f$ | %%1: %9s$ DD%%%.1f | prop: risk %%%.2f "
          "-> %8s$"
          % (label, cost_name, len(d), 100 * (d.r > 0).mean(), d.r.sum(),
             d[isk].r.sum(), d[~isk].r.sum(), d.dur_h.median(),
             d.stop.median(),
             format(e["final"], ",.0f").replace(",", "."), e["dd"],
             fp * 100, format(ep["final"], ",.0f").replace(",", ".")),
          flush=True)


def main() -> None:
    print("KONTROL — mevcut ayar + BingX maliyeti, +134.4R uretmeli\n",
          flush=True)
    base = run(None, None, None, COSTS["BingX VIP0"])
    report("mevcut (kontrol)", "BingX VIP0", base)
    if abs(base.r.sum() - BASE_TOP) > 0.5:
        print("  !! KONTROL BASARISIZ (beklenen %+.1f) — cikiliyor" % BASE_TOP)
        return
    print("  -> kontrol GECTI\n", flush=True)

    for cname, cost in COSTS.items():
        print("--- maliyet profili: %s ---" % cname, flush=True)
        for label, swing, rr, teb in VARIANTS:
            try:
                d = run(swing, rr, teb, cost)
                if not d.empty:
                    d.to_csv(ROOT / "reports" /
                             ("scalp__%s__%s.csv" % (slug(cname), slug(label))),
                             index=False)
                report(label, cname, d)
            except Exception as ex:
                print("  %-22s %-11s HATA: %s" % (label, cname, ex))
        print(flush=True)
    print("BITTI")


if __name__ == "__main__":
    main()
