# -*- coding: utf-8 -*-
"""
HIBRIT RR — giris saatine gore hedef secimi
============================================
BULGU (overlap_rr_lab): Londra-NY ortusme penceresinde acilan islemlerde
KISA RR uzun RR'yi acik ara geciyor (1:2 > 1:5, uc pencerede de). Sistemin
genelinde tersi (1:5, 1:2'nin iki kati).

SEBEP (dr_session_lab): NY onden-yuklu (ekstremumlarin %62'si ilk 1/3'te),
gunun ekstremumu ortusmede 2.2 kat yogun. O pencerede acilan islem hedefine
HIZLI gider ya da hic gitmez -> uzun hedef bosa bekler.

BU TEST filtre DEGIL: islem SAYISI degismez, yalniz TP mesafesi degisir.
  giris saati pencerede -> kisa RR
  disarida              -> config'teki uzun RR
Motor bellekte yamanir (RiskManager.compute), disk degismez.

Kural: IS ve OOS'ta BIRLIKTE iyilesme + riske-normalize kazanc.
"""
from __future__ import annotations
import sys, types
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from equity import event_equity, risk_for_dd

SRC = ROOT / "xauusd_fvg_engine_v10.py"
MODNAME = "xauusd_fvg_engine_v10"
SPLIT = pd.Timestamp("2025-01-11")
STRATS = ["fvg", "harmonic", "threevol", "fib"]

# 1) RiskManager.compute'a saat-bilincli rr
A1 = """    def compute(self, direction: str, entry: float,
                stop_price: float, equity: float,
                risk_fraction: float,
                tp_override: Optional[float] = None) -> Optional[Dict]:

        if direction == 'bull':
            sl   = stop_price * (1.0 - self.sl_buffer)
            risk = abs(entry - sl)
            tp   = tp_override if tp_override is not None else entry + risk * self.rr
        else:
            sl   = stop_price * (1.0 + self.sl_buffer)
            risk = abs(sl - entry)
            tp   = tp_override if tp_override is not None else entry - risk * self.rr"""
B1 = """    def compute(self, direction: str, entry: float,
                stop_price: float, equity: float,
                risk_fraction: float,
                tp_override: Optional[float] = None) -> Optional[Dict]:

        _rr = self.rr
        if _HIB_SAAT and _HIB_NOW[0] is not None and _HIB_NOW[0] in _HIB_SAAT:
            _rr = _HIB_RR
        if direction == 'bull':
            sl   = stop_price * (1.0 - self.sl_buffer)
            risk = abs(entry - sl)
            tp   = tp_override if tp_override is not None else entry + risk * _rr
        else:
            sl   = stop_price * (1.0 + self.sl_buffer)
            risk = abs(sl - entry)
            tp   = tp_override if tp_override is not None else entry - risk * _rr"""

# 2) giris barinin saatini kaydet (compute cagrilmadan hemen once)
A2 = """        for idx in bt_idx:
            if idx + 1 >= len(df5):
                break"""
B2 = """        for idx in bt_idx:
            if idx + 1 >= len(df5):
                break
            if _HIB_SAAT:
                _HIB_NOW[0] = to_naive(TM[min(idx + 1, len(TM) - 1)]).hour"""


def yukle(saatler, rr):
    src = SRC.read_text(encoding="utf-8")
    for a, b in ((A1, B1), (A2, B2)):
        if src.count(a) != 1:
            raise SystemExit("cipa eslesmedi (%d kez)" % src.count(a))
        src = src.replace(a, b, 1)
    src = ("_HIB_SAAT = %r\n_HIB_RR = %r\n_HIB_NOW = [None]\n"
           % (list(saatler), float(rr))) + src
    for m in (MODNAME, "gui", "config"):
        sys.modules.pop(m, None)
    mod = types.ModuleType(MODNAME); mod.__file__ = str(SRC)
    sys.modules[MODNAME] = mod
    exec(compile(src, str(SRC), "exec"), mod.__dict__)


def kosu(saatler, rr):
    yukle(saatler, rr)
    import gui
    from xauusd_fvg_engine_v10 import to_naive
    rows = []
    for s in STRATS:
        r = gui._run_strategy(s, keep_trades=True)[0]
        for t in r.get("_trades", []):
            if t.exit_time is None or t.risk_dollar <= 0:
                continue
            e = pd.Timestamp(str(to_naive(t.signal.entry_time))[:19])
            rows.append(dict(entry=e, exit=pd.Timestamp(str(to_naive(t.exit_time))[:19]),
                             r=t.pnl_dollar / t.risk_dollar, saat=e.hour))
    return pd.DataFrame(rows).sort_values("exit").reset_index(drop=True)


def main():
    print("KONTROL — hibrit kapali", flush=True)
    b = kosu([], 2.0)
    bi, bo = b[b.entry < SPLIT].r.sum(), b[b.entry >= SPLIT].r.sum()
    eb = event_equity(b, 0.01)
    nb = event_equity(b, risk_for_dd(b, eb["dd"]))["final"]
    print("  N=%d IS=%+.1f OOS=%+.1f TOP=%+.1f bakiye=%s$ DD=%.1f%%\n"
          % (len(b), bi, bo, bi + bo,
             format(eb["final"], ",.0f").replace(",", "."), eb["dd"]), flush=True)
    if abs(bi + bo - 166.6) > 0.5:
        print("  !! KONTROL BASARISIZ (beklenen +166.6R) — cikiliyor"); return
    print("  -> kontrol GECTI\n", flush=True)

    for pad, saatler in (("ortusme 13-16", [13, 14, 15]),
                         ("genis 12-17", [12, 13, 14, 15, 16]),
                         ("NY on 13-18", [13, 14, 15, 16, 17])):
        for rr in (1.0, 1.5, 2.0, 3.0):
            d = kosu(saatler, rr)
            i, o = d[d.entry < SPLIT].r.sum(), d[d.entry >= SPLIT].r.sum()
            e = event_equity(d, 0.01)
            n = event_equity(d, risk_for_dd(d, eb["dd"]))["final"]
            ic = d[d.saat.isin(saatler)]
            print("  %-14s kisa RR 1:%.1f  N=%3d (pencerede %3d) IS=%+6.1f(%+5.1f) "
                  "OOS=%+6.1f(%+5.1f) TOP=%+6.1f bakiye=%8s$ DD=%4.1f%% "
                  "esit-riskte=%8s$ (%+.0f%%)%s"
                  % (pad, rr, len(d), len(ic), i, i - bi, o, o - bo, i + o,
                     format(e["final"], ",.0f").replace(",", "."), e["dd"],
                     format(n, ",.0f").replace(",", "."), 100 * (n / nb - 1),
                     "  <<< KABUL" if (i > bi and o > bo and n > nb) else ""),
                  flush=True)
        print(flush=True)
    print("BITTI")


if __name__ == "__main__":
    main()
