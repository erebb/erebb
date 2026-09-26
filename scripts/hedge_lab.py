# -*- coding: utf-8 -*-
"""
HEDGE LABORATUVARI — açık işlem varken TERS yönde sinyal gelirse al
====================================================================
Motor ve config'e DOKUNULMAZ; kaynak bellekte yamanır.

ÖNEMLİ YAPISAL GERÇEK: mevcut sistemde hedge zaten İMKÂNSIZ. Günlük SMA200
kapısı (trend_gate) ana trende karşı her sinyali reddeder — yani aynı anda
iki yönde sinyal hiç oluşmaz. Bu laboratuvar kapıyı YALNIZCA hedge girişi
için deler: açık işlemin tersi yönde bir sinyal varsa, o sinyal trend
kapısını atlayabilir ve ikinci pozisyon olarak açılır.

Kural
-----
  havuz boşsa            -> normal giriş (trend kapısı geçerli)
  havuzda 1 işlem varsa  -> yalnız TERS yönde ikinci giriş (hedge)
  havuz 2 doluysa        -> giriş yok

EKONOMİK UYARI: tek enstrümanda long+short aynı anda, ikisi açıkken net
pozisyonu düzleştirir ama HER İKİ tarafın spread+komisyonu ödenir. Risk
azaltmaz; iki zıt bahsi aynı anda taşımak için para ödemektir. Kâr ancak
biri stop olup diğeri koşarsa çıkar.

CANLI UYARISI: BingX vadeli işlemlerde aynı sembolde iki yönü birden
taşımak "hedge mode" gerektirir; tek-yön (one-way) modda ters emir mevcut
pozisyonu KAPATIR. Kabul edilirse canlı tarafta bu ayar şarttır.

Kontrol: hedge kapalı -> mevcut sistemi birebir üretmeli (TOP=+134.4R).
Kullanım: python3 scripts/hedge_lab.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

SRC = ROOT / "xauusd_fvg_engine_v10.py"
MODNAME = "xauusd_fvg_engine_v10"
SPLIT = pd.Timestamp("2025-01-11")
STRATS = ["fvg", "harmonic", "threevol", "fib"]
BASE_TOP = 134.4

from concurrency_lab import PATCHES as POOL_PATCHES, _concurrency, _bal_at_dd

# concurrency_lab'ın havuz yamalarından kapasiteye BAĞLI olanları ayıkla;
# 1,2,3,5,6,9,10 saf liste dönüşümüdür ve aynen kullanılır.
_POOL_KEEP = [p for p in POOL_PATCHES if "_LAB_MAX" not in p[1]]

_ALLOW = ("""(len(_pool) == 0 or (_LAB_HEDGE and len(_pool) < 2 and
                     all(_x.signal.direction != %s for _x in _pool)))""")

HEDGE_PATCHES = [
    # bekleyen limit: havuz boş VEYA ters yönde tek işlem var
    ("""                slot_free = (active_prz is None if pl['is_prz']
                             else active_fvg is None)""",
     """                _pool = active_prz if pl['is_prz'] else active_fvg
                slot_free = """ + (_ALLOW % "pl['signal'].direction")),

    # her iki havuz da tam doluysa sinyal arama
    ("""            if active_fvg is not None and active_prz is not None:
                continue""",
     """            if len(active_fvg) >= 2 and len(active_prz) >= 2:
                continue"""),

    # trend kapısı: hedge girişi için delinir
    ("""                td = int(self.trend_gate[idx])
                want = 1 if signal.direction == 'bull' else -1
                if td != want:""",
     """                td = int(self.trend_gate[idx])
                want = 1 if signal.direction == 'bull' else -1
                _hopen = [_x for _x in (list(active_fvg) + list(active_prz))
                          if _x.signal.direction != signal.direction]
                if td != want and not (_LAB_HEDGE and _hopen):"""),

    # sinyal yönlendirme
    ("""            if is_prz and active_prz is not None:
                continue   # PRZ slot dolu; FVG slot serbest ama PRZ sinyali geldi
            if not is_prz and active_fvg is not None:
                continue   # FVG slot dolu; PRZ slot serbest ama FVG sinyali geldi""",
     """            _pool = active_prz if is_prz else active_fvg
            if not """ + (_ALLOW % "signal.direction") + """:
                continue"""),
]


def load_patched(hedge: bool) -> None:
    src = SRC.read_text(encoding="utf-8")
    for i, (a, b) in enumerate(_POOL_KEEP + HEDGE_PATCHES, 1):
        if src.count(a) != 1:
            raise SystemExit("yama %d eslesmedi (%d kez) — motor degismis"
                             % (i, src.count(a)))
        src = src.replace(a, b, 1)
    src = ("_LAB_HEDGE = %r\n" % bool(hedge)) + src
    for m in list(sys.modules):
        if m in (MODNAME, "gui", "config"):
            del sys.modules[m]
    mod = types.ModuleType(MODNAME)
    mod.__file__ = str(SRC)
    sys.modules[MODNAME] = mod
    exec(compile(src, str(SRC), "exec"), mod.__dict__)


def run(hedge: bool) -> pd.DataFrame:
    load_patched(hedge)
    sys.path.insert(0, str(ROOT))
    import gui
    rows = []
    for s in STRATS:
        r = gui._run_strategy(s, keep_trades=True)[0]
        for t in r.get("_trades", []):
            if t.exit_time is None or t.risk_dollar <= 0:
                continue
            rows.append(dict(s=s,
                             entry=pd.Timestamp(str(t.signal.entry_time)[:19]),
                             exit=pd.Timestamp(str(t.exit_time)[:19]),
                             r=t.pnl_dollar / t.risk_dollar,
                             px=t.entry_price, dir=t.signal.direction,
                             reason=getattr(t, "exit_reason", "")))
    d = pd.DataFrame(rows).sort_values("exit").reset_index(drop=True)
    d.to_csv(ROOT / "reports" / ("hedge_ledger_%s.csv"
                                 % ("on" if hedge else "off")), index=False)
    return d


def report(name: str, d: pd.DataFrame, base=None) -> dict:
    isk = d.entry < SPLIT
    bal, c = 10000.0, []
    for x in d.r:
        bal *= (1 + 0.01 * x)
        c.append(bal)
    cs = pd.Series(c)
    dd = abs((cs / cs.cummax() - 1).min()) * 100
    norm = _bal_at_dd(d, 12.3)
    ca, cm = _concurrency(d)
    tail = ""
    if base:
        g = norm / base["norm"] - 1
        tail = ("  ->  esit riskte %+.1f%%  %s"
                % (100 * g, "KABUL" if g > 0 else "ELENDI"))
    print("%-12s N=%3d IS=%+6.1f OOS=%+6.1f TOP=%+6.1f WR=%4.1f%% "
          "bakiye=%s$ maxDD=%%%.1f esit-riskte=%s$ es-zaman %.2f/%d%s"
          % (name, len(d), d[isk].r.sum(), d[~isk].r.sum(), d.r.sum(),
             100 * (d.r > 0).mean(),
             format(bal, ",.0f").replace(",", "."), dd,
             format(norm, ",.0f").replace(",", "."), ca, cm, tail), flush=True)
    return dict(r=d.r.sum(), norm=norm)


def main() -> None:
    print("KONTROL — hedge kapali, mevcut sistemi birebir uretmeli", flush=True)
    off = run(False)
    b = report("hedge KAPALI", off)
    if abs(b["r"] - BASE_TOP) > 0.5:
        print("  !! KONTROL BASARISIZ (beklenen %+.1f) — cikiliyor" % BASE_TOP)
        return
    print("  -> kontrol GECTI\n", flush=True)

    on = run(True)
    report("hedge ACIK", on, b)

    # hedge işlemlerini ayıkla: kapalı koşuda olmayan, ters yönlü girişler
    k = set(zip(off.s, off.entry.astype(str), off.px.round(2)))
    new = on[[(s, str(e), round(p, 2)) not in k
              for s, e, p in zip(on.s, on.entry, on.px)]]
    print("\nHEDGE ISLEMLERI: %d adet, toplam %+.1fR (islem basi %+.3fR)"
          % (len(new), new.r.sum(), new.r.mean() if len(new) else 0))
    if len(new):
        print("  yon dagilimi:", dict(new.groupby("dir").size()))
        print("  cikis nedeni:", dict(new.groupby("reason").size()))
        print("  strateji     :", dict(new.groupby("s").r.agg(["size", "sum"])
                                       .round(1).to_dict("index")))
    print("BITTI")


if __name__ == "__main__":
    main()
