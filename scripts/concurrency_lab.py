# -*- coding: utf-8 -*-
"""
EŞ-ZAMANLI POZİSYON LABORATUVARI — motora DOKUNMADAN
=====================================================
Soru: sinyal geldiğinde açık işlem varken de girsek ne olur?

Mevcut motor iki TEK-kişilik slot tutar: 'fvg' (FVG/OB girişleri) ve 'prz'
(harmonik girişler). Slot doluyken gelen sinyal ATLANIR. Bu laboratuvar o
slotları KAPASİTELİ HAVUZA çevirir (havuz başına en fazla N işlem).

Yöntem: motorun kaynağı okunur, BELLEKTE yamanır, sys.modules'e enjekte
edilir. Diskteki xauusd_fvg_engine_v10.py / gui.py / config DEĞİŞMEZ.

RİSK UYARISI — bu, saf bir "daha çok işlem" testi DEĞİL:
her işlem o anki bakiyenin %1'ini riske attığı için N eş-zamanlı işlem
demek, aynı anda %N açık risk demek. Bu yüzden rapor yalnız R toplamını
değil, BİLEŞİK BAKİYEYİ ve MAKS. DÜŞÜŞÜ de basar. R artıp düşüş daha çok
artıyorsa mekanizma kabul edilmez.

Ayrıca: 'pending_limit' motorda TEK bir bekleyen emirdir; bu laboratuvar
onu değiştirmez. Yani aynı anda birden çok limit emri beklemez — eş-zamanlılık
ancak bekleyen emir dolduktan sonra artabilir. Sonuç bu yüzden temkinlidir.

Kural: IS (<2025-01-11) ve OOS'ta BİRLİKTE iyileşmeyen aday elenir.
Her koşu önce KONTROL yapar (N=1 → mevcut sistemi birebir üretmeli).

Kullanım:
    python3 scripts/concurrency_lab.py 2 3 5
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "xauusd_fvg_engine_v10.py"
MODNAME = "xauusd_fvg_engine_v10"
SPLIT = pd.Timestamp("2025-01-11")
STRATS = ["fvg", "harmonic", "threevol", "fib"]
BASE_TOP = 134.4

# ── (çıpa, yerine) çiftleri — hepsi birebir eşleşmeli ──────────────────────
PATCHES = [
    # 1) slot değişkenleri → havuz listeleri
    ("""        active_fvg: Optional[Trade] = None   # FVG/ana slot (PRZ olmayan)
        active_prz: Optional[Trade] = None   # Harmonik PRZ slot""",
     """        active_fvg: list = []   # [LAB] FVG/ana havuz
        active_prz: list = []   # [LAB] harmonik PRZ havuzu"""),

    # 2) çıkış döngüsü: (slot, işlem) çiftleri üzerinde dön — gövde
    #    girintisi korunur, bu yüzden alt blok hiç değişmez
    ("""            for slot_key in ('fvg', 'prz'):
                t = active_fvg if slot_key == 'fvg' else active_prz
                if t is None:
                    continue""",
     """            for slot_key, t in ([('fvg', _x) for _x in list(active_fvg)] +
                                [('prz', _x) for _x in list(active_prz)]):
                if t is None:
                    continue"""),

    # 3) çıkışta havuzdan çıkar
    ("""                    if slot_key == 'fvg':
                        active_fvg = None
                    else:
                        active_prz = None""",
     """                    if slot_key == 'fvg':
                        active_fvg.remove(t)
                    else:
                        active_prz.remove(t)"""),

    # 4) bekleyen limit: havuzda yer var mı
    ("""                slot_free = (active_prz is None if pl['is_prz']
                             else active_fvg is None)""",
     """                slot_free = (len(active_prz) < _LAB_MAX if pl['is_prz']
                             else len(active_fvg) < _LAB_MAX)"""),

    # 5) limit dolumu → havuza ekle
    ("""                        if pl['is_prz']:
                            active_prz = t_new
                        else:
                            active_fvg = t_new""",
     """                        if pl['is_prz']:
                            active_prz.append(t_new)
                        else:
                            active_fvg.append(t_new)"""),

    # 6) dolum barında hemen çıktıysa havuzdan çıkar
    ("""                            if pl['is_prz']:
                                active_prz = None
                            else:
                                active_fvg = None""",
     """                            if pl['is_prz']:
                                active_prz.remove(t_new)
                            else:
                                active_fvg.remove(t_new)"""),

    # 7) her iki havuz da doluysa sinyal arama
    ("""            if active_fvg is not None and active_prz is not None:
                continue""",
     """            if len(active_fvg) >= _LAB_MAX and len(active_prz) >= _LAB_MAX:
                continue"""),

    # 8) sinyal yönlendirme
    ("""            if is_prz and active_prz is not None:
                continue   # PRZ slot dolu; FVG slot serbest ama PRZ sinyali geldi
            if not is_prz and active_fvg is not None:
                continue   # FVG slot dolu; PRZ slot serbest ama FVG sinyali geldi""",
     """            if is_prz and len(active_prz) >= _LAB_MAX:
                continue
            if not is_prz and len(active_fvg) >= _LAB_MAX:
                continue"""),

    # 9) market girişi → havuza ekle
    ("""            if is_prz:
                active_prz = new_trade
            else:
                active_fvg = new_trade""",
     """            if is_prz:
                active_prz.append(new_trade)
            else:
                active_fvg.append(new_trade)"""),

    # 10) dönem sonu açık işlemler
    ("""        for t in (active_fvg, active_prz):
            if t is not None:""",
     """        for t in (list(active_fvg) + list(active_prz)):
            if t is not None:"""),
]


def load_patched(nmax: int) -> None:
    src = SRC.read_text(encoding="utf-8")
    for i, (a, b) in enumerate(PATCHES, 1):
        if src.count(a) != 1:
            raise SystemExit("yama %d eslesmedi (%d kez bulundu) — motor "
                             "degismis, scripts/concurrency_lab.py guncellenmeli"
                             % (i, src.count(a)))
        src = src.replace(a, b, 1)
    src = ("_LAB_MAX = %d\n" % int(nmax)) + src

    for m in list(sys.modules):
        if m in (MODNAME, "gui", "config"):
            del sys.modules[m]
    mod = types.ModuleType(MODNAME)
    mod.__file__ = str(SRC)
    sys.modules[MODNAME] = mod
    exec(compile(src, str(SRC), "exec"), mod.__dict__)


def run(nmax: int) -> pd.DataFrame:
    load_patched(nmax)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "scripts"))
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
                             reason=getattr(t, "exit_reason", "")))
    return pd.DataFrame(rows).sort_values("exit").reset_index(drop=True)


def stats(d: pd.DataFrame) -> dict:
    isk = d.entry < SPLIT
    bal, curve = 10000.0, []
    for x in d.r:
        bal *= (1 + 0.01 * x)
        curve.append(bal)
    c = pd.Series(curve)
    # aynı anda kaç işlem açıktı
    conc = [int(((d.entry < r.exit) & (d["exit"] > r.entry)).sum())
            for r in d.itertuples()]
    return dict(n=len(d), is_r=d[isk].r.sum(), oos_r=d[~isk].r.sum(),
                r=d.r.sum(), wr=100 * (d.r > 0).mean(), bal=bal,
                dd=abs((c / c.cummax() - 1).min()) * 100,
                conc=float(np.mean(conc)), cmax=int(np.max(conc)))


def show(name: str, m: dict, base=None) -> None:
    d = ""
    ok = ""
    if base:
        d = " (TOP %+.1f)" % (m["r"] - base["r"])
        # kabul: IS+OOS birlikte artmali VE düşüş getiriden daha hizli
        # artmamali (risk-ayarli iyilesme sarti)
        better = m["is_r"] > base["is_r"] and m["oos_r"] > base["oos_r"]
        eff = (m["bal"] / base["bal"]) >= (m["dd"] / base["dd"])
        ok = "  <<< KABUL" if (better and eff) else ("  (R arttı ama düşüş "
                                                     "daha hızlı arttı)"
                                                     if better else "")
    print("%-14s N=%3d IS=%+6.1f OOS=%+6.1f TOP=%+6.1f%s WR=%4.1f%% "
          "bakiye=%s$ maxDD=%%%.1f  ortalama es-zaman=%.2f (en fazla %d)%s"
          % (name, m["n"], m["is_r"], m["oos_r"], m["r"], d, m["wr"],
             format(m["bal"], ",.0f").replace(",", "."), m["dd"],
             m["conc"], m["cmax"], ok), flush=True)


def main() -> None:
    levels = [int(x) for x in sys.argv[1:]] or [2, 3, 5]

    print("KONTROL — N=1, mevcut sistemi birebir üretmeli", flush=True)
    b = stats(run(1))
    show("N=1 referans", b)
    if abs(b["r"] - BASE_TOP) > 0.5:
        print("  !! KONTROL BASARISIZ (beklenen TOP=%+.1f) — cikiliyor"
              % BASE_TOP)
        return
    print("  -> kontrol GECTI\n", flush=True)

    for n in levels:
        show("N=%d" % n, stats(run(n)), b)
    print("BITTI")


if __name__ == "__main__":
    main()
