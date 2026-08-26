# -*- coding: utf-8 -*-
"""
SEANS BIAS LABORATUVARI
========================
Kullanicinin seans gozlemlerini BIAS FILTRESINE cevirip test eder.
TEST AMACLIDIR: motor/config diske yazilmaz; gui.py bellekte yamanip
'session' bias modu tanitilir.

OLCULEN GERCEKLER (scripts/session_lab.py, 1274 is gunu):
  uc seans ayni yon %39.4 | Londra=NY %74.5 | Tokyo=Londra %53.2
  Tokyo teyit degeri GOSTERILEMIYOR (Londra=NY orani Tokyo uyumluyken
  %74.0, ters iken %75.0 -> guven araliklari ortusuyor)

VARYANTLAR (hepsi yalniz KAPANMIS seanslari okur -> nedensel):
  londra / tokyo / teyit (Tokyo==Londra) / manip (NY'de Londra yonunun
  tersine >=XxATR hareket olduysa Londra yonunde bias)

Kural: IS (<2025-01-11) ve OOS'ta BIRLIKTE iyilesmeyen aday elenir.
"""
from __future__ import annotations
import sys, types
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from equity import event_equity          # sys.modules oyunlarindan ONCE

STRATS = ["fvg", "harmonic", "threevol", "fib"]
SPLIT = pd.Timestamp("2025-01-11")
SEANS = {"Tokyo": (0, 8), "Londra": (7, 16), "NY": (12, 21)}


class SessionBias:
    """get(dt) -> 'bull' | 'bear' | None  (BiasProvider sozlesmesi)."""

    def __init__(self, df5, mod, manip_atr=0.15):
        self.mod, self.manip_atr = mod, manip_atr
        idx = pd.to_datetime(df5.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        d = df5.copy(); d.index = idx; self.df = d
        gun = idx.normalize()
        g = d.groupby(gun).agg(H=("High", "max"), L=("Low", "min"))
        atr = (g.H - g.L).rolling(14).mean().shift(1)      # NEDENSEL
        rec = {}
        for day, gg in d.groupby(gun):
            r = {"atr": float(atr.get(day, np.nan))}
            for ad, (a, b) in SEANS.items():
                s = gg[(gg.index.hour >= a) & (gg.index.hour < b)]
                if len(s) < 12:
                    continue
                r[ad] = 1 if float(s.Close.iloc[-1]) > float(s.Open.iloc[0]) else -1
                r[ad + "_bit"] = s.index[-1]
                r[ad + "_ac"] = float(s.Open.iloc[0])
            rec[pd.Timestamp(day)] = r
        self.rec = rec
        self.gunler = sorted(rec)

    def _son_kapali(self, t, ad):
        for day in reversed(self.gunler):
            if day > t:
                continue
            r = self.rec.get(day, {})
            bit = r.get(ad + "_bit")
            if bit is not None and bit < t and ad in r:
                return r[ad], day
            if day < t.normalize() - pd.Timedelta(days=5):
                break
        return None, None

    def get(self, dt):
        t = pd.Timestamp(str(dt)[:19])
        if self.mod == "londra":
            y, _ = self._son_kapali(t, "Londra")
        elif self.mod == "tokyo":
            y, _ = self._son_kapali(t, "Tokyo")
        elif self.mod == "teyit":
            a, _ = self._son_kapali(t, "Tokyo")
            b, _ = self._son_kapali(t, "Londra")
            y = a if (a is not None and a == b) else None
        elif self.mod == "manip":
            b, gun = self._son_kapali(t, "Londra")
            if b is None:
                return None
            r = self.rec.get(gun, {}); atr = r.get("atr", np.nan)
            ac = r.get("NY_ac")
            if not (atr == atr) or ac is None:
                return None
            w = self.df[(self.df.index >= gun + pd.Timedelta(hours=12))
                        & (self.df.index < t)]
            if w.empty:
                return None
            ters = (ac - float(w.Low.min())) if b == 1 else (float(w.High.max()) - ac)
            y = b if ters >= self.manip_atr * atr else None
        else:
            y = None
        return None if y is None else ("bull" if y > 0 else "bear")


def yukle_gui():
    """gui.py'yi bellekte yamala: make_bias'a 'session' modu ekle."""
    src = (ROOT / "gui.py").read_text(encoding="utf-8")
    a = '        if mode == "private": return PrivateBiasProvider(df_1h)'
    if src.count(a) != 1:
        raise SystemExit("cipa bulunamadi — gui.make_bias degismis")
    src = src.replace(a, '        if mode == "session": return _SESSION_BIAS\n' + a)
    sys.modules.pop("gui", None)
    m = types.ModuleType("gui"); m.__file__ = str(ROOT / "gui.py")
    m.__dict__["_SESSION_BIAS"] = None
    sys.modules["gui"] = m
    exec(compile(src, str(ROOT / "gui.py"), "exec"), m.__dict__)
    return m


def kosu(gui, bias_obj):
    from xauusd_fvg_engine_v10 import to_naive
    gui.__dict__["_SESSION_BIAS"] = bias_obj
    rows = []
    for s in STRATS:
        r = gui._run_strategy(s, keep_trades=True)[0]
        for t in r.get("_trades", []):
            if t.exit_time is None or t.risk_dollar <= 0:
                continue
            rows.append(dict(entry=pd.Timestamp(str(to_naive(t.signal.entry_time))[:19]),
                             exit=pd.Timestamp(str(to_naive(t.exit_time))[:19]),
                             r=t.pnl_dollar / t.risk_dollar))
    return pd.DataFrame(rows).sort_values("exit").reset_index(drop=True)


def main():
    gui = yukle_gui()
    from config import get_config
    cfg = get_config()
    _df1h, df5, _ = gui._load_data()

    baz = kosu(gui, None)
    bi, bo = baz[baz.entry < SPLIT].r.sum(), baz[baz.entry >= SPLIT].r.sum()
    eb = event_equity(baz, 0.01)
    print("BAZ (bias yok)  N=%d IS=%+.1f OOS=%+.1f TOP=%+.1f bakiye=%s$\n"
          % (len(baz), bi, bo, bi + bo,
             format(eb["final"], ",.0f").replace(",", ".")), flush=True)

    keep = {s: cfg.get(s, "bias", default="none") for s in STRATS}
    for s in STRATS:
        cfg.set(s, "bias", "session")
    try:
        for et, md, kw in [("Londra yonu", "londra", {}),
                           ("Tokyo yonu", "tokyo", {}),
                           ("Tokyo+Londra teyit", "teyit", {}),
                           ("NY manip 0.10xATR", "manip", dict(manip_atr=0.10)),
                           ("NY manip 0.15xATR", "manip", dict(manip_atr=0.15)),
                           ("NY manip 0.20xATR", "manip", dict(manip_atr=0.20))]:
            d = kosu(gui, SessionBias(df5, md, **kw))
            if d.empty:
                print("  %-20s islem yok" % et, flush=True); continue
            i, o = d[d.entry < SPLIT].r.sum(), d[d.entry >= SPLIT].r.sum()
            e = event_equity(d, 0.01)
            print("  %-20s N=%3d IS=%+6.1f(%+5.1f) OOS=%+6.1f(%+5.1f) "
                  "TOP=%+6.1f(%+5.1f) bakiye=%8s$%s"
                  % (et, len(d), i, i - bi, o, o - bo, i + o, i + o - bi - bo,
                     format(e["final"], ",.0f").replace(",", "."),
                     "  <<< KABUL" if (i > bi and o > bo) else ""), flush=True)
    finally:
        for s in STRATS:
            cfg.set(s, "bias", keep[s])
    print("BITTI")


if __name__ == "__main__":
    main()
