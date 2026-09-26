# -*- coding: utf-8 -*-
"""
YONLU GUNLUK DEVRE KESICI
==========================
Kural: ayni yonde ust uste N stop olunca, O GUN o yonde yeni islem alma.

TEST AMACLIDIR — motor bellekte yamanir, disk degismez.
Daha once elenen devre kesicilerden FARKI: onlar yonden bagimsizdi
(aylik / ardisik kayip). Bu, yon bazinda ve gunluk.

Varyantlar:
  N = 2 veya 3 ardisik stop
  sayac_sifirlama = 'kazanc' (o yonde kazanc gelince sifirlanir)
                  | 'gun'    (her gun basinda da sifirlanir)

NEDENSELLIK: sayac yalniz KAPANMIS islemlerle guncellenir; blok, kapanis
barindan SONRAKI girisler icin gecerlidir.

Kural: IS (<2025-01-11) ve OOS'ta BIRLIKTE iyilesmeyen aday elenir.
Olcut riske-normalize: ayni maks. dususte daha cok para mi?
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

# 1) sayac/blok durumunu kur (run() basinda)
A1 = """        active_fvg: Optional[Trade] = None   # FVG/ana slot (PRZ olmayan)"""
B1 = """        _brk_cnt = {'bull': 0, 'bear': 0}     # [LAB] ardisik stop sayaci
        _brk_blok = {'bull': None, 'bear': None}  # [LAB] blokli gun
        active_fvg: Optional[Trade] = None   # FVG/ana slot (PRZ olmayan)"""

# 2) cikista sayaci guncelle
A2 = """                if exited:
                    t.equity_after  = round(equity, 2)
                    trades.append(t)
                    if slot_key == 'fvg':"""
B2 = """                if exited:
                    if _LAB_N > 0:
                        _d = t.signal.direction
                        if getattr(t, 'exit_reason', '') == 'sl':
                            _brk_cnt[_d] += 1
                            if _brk_cnt[_d] >= _LAB_N:
                                _brk_blok[_d] = to_naive(TM[idx]).date()
                        else:
                            _brk_cnt[_d] = 0
                    t.equity_after  = round(equity, 2)
                    trades.append(t)
                    if slot_key == 'fvg':"""

# 3) giriste blogu uygula (trend kapisindan hemen sonra)
A3 = """            # ── Saat karartması (blackout): bu UTC saatlerinde giriş yok ────"""
B3 = """            if _LAB_N > 0:
                _d = signal.direction
                _bugun = to_naive(TM[idx]).date()
                if _LAB_RESET == 'gun' and _brk_blok[_d] not in (None, _bugun):
                    _brk_cnt[_d] = 0
                    _brk_blok[_d] = None
                if _brk_blok[_d] == _bugun:
                    dbg['no_signal'] += 1
                    continue

            # ── Saat karartması (blackout): bu UTC saatlerinde giriş yok ────"""


def yukle(n: int, reset: str):
    src = SRC.read_text(encoding="utf-8")
    for a, b in ((A1, B1), (A2, B2), (A3, B3)):
        if src.count(a) != 1:
            raise SystemExit("cipa eslesmedi (%d) — motor degismis" % src.count(a))
        src = src.replace(a, b, 1)
    src = ("_LAB_N = %d\n_LAB_RESET = %r\n" % (n, reset)) + src
    for m in (MODNAME, "gui", "config"):
        sys.modules.pop(m, None)
    mod = types.ModuleType(MODNAME); mod.__file__ = str(SRC)
    sys.modules[MODNAME] = mod
    exec(compile(src, str(SRC), "exec"), mod.__dict__)


def kosu(n: int, reset: str = "kazanc") -> pd.DataFrame:
    yukle(n, reset)
    import gui
    from xauusd_fvg_engine_v10 import to_naive
    rows = []
    for s in STRATS:
        r = gui._run_strategy(s, keep_trades=True)[0]
        for t in r.get("_trades", []):
            if t.exit_time is None or t.risk_dollar <= 0:
                continue
            rows.append(dict(entry=pd.Timestamp(str(to_naive(t.signal.entry_time))[:19]),
                             exit=pd.Timestamp(str(to_naive(t.exit_time))[:19]),
                             r=t.pnl_dollar / t.risk_dollar,
                             dir=t.signal.direction,
                             reason=getattr(t, "exit_reason", "")))
    return pd.DataFrame(rows).sort_values("exit").reset_index(drop=True)


def main():
    print("KONTROL — kural kapali (N=0)", flush=True)
    b = kosu(0)
    bi, bo = b[b.entry < SPLIT].r.sum(), b[b.entry >= SPLIT].r.sum()
    eb = event_equity(b, 0.01)
    nb = event_equity(b, risk_for_dd(b, eb["dd"]))
    print("  N=%d IS=%+.1f OOS=%+.1f TOP=%+.1f bakiye=%s$ DD=%.1f%%\n"
          % (len(b), bi, bo, bi + bo,
             format(eb["final"], ",.0f").replace(",", "."), eb["dd"]), flush=True)

    for n in (2, 3):
        for reset in ("kazanc", "gun"):
            d = kosu(n, reset)
            i, o = d[d.entry < SPLIT].r.sum(), d[d.entry >= SPLIT].r.sum()
            e = event_equity(d, 0.01)
            nn = event_equity(d, risk_for_dd(d, eb["dd"]))
            g = nn["final"] / nb["final"] - 1
            print("  N=%d sifirlama=%-7s  islem=%3d(-%2d) IS=%+6.1f(%+5.1f) "
                  "OOS=%+6.1f(%+5.1f) TOP=%+6.1f(%+5.1f) bakiye=%8s$ DD=%4.1f%% "
                  "esit-riskte=%8s$ (%+.1f%%)  %s"
                  % (n, reset, len(d), len(b) - len(d), i, i - bi, o, o - bo,
                     i + o, i + o - bi - bo,
                     format(e["final"], ",.0f").replace(",", "."), e["dd"],
                     format(nn["final"], ",.0f").replace(",", "."), 100 * g,
                     "KABUL" if (i > bi and o > bo and g > 0) else "ELENDI"),
                  flush=True)
    print("BITTI")


if __name__ == "__main__":
    main()
