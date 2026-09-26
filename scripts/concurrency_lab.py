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
                             px=t.entry_price, sl=t.sl,
                             dir=t.signal.direction,
                             conf=getattr(t.signal, "confirmation_type", ""),
                             reason=getattr(t, "exit_reason", "")))
    d = pd.DataFrame(rows).sort_values("exit").reset_index(drop=True)
    d.to_csv(ROOT / "reports" / ("conc_ledger_N%d.csv" % nmax), index=False)
    return d


DD_TARGET = 12.3          # mevcut sistemin maks. düşüşü (%) — normalize hedefi


def _concurrency(d: pd.DataFrame) -> tuple:
    """(zaman-ağırlıklı ortalama, tepe) açık pozisyon sayısı.
    Olay taraması — işlem başına 'kendini de say' hatası yapmaz."""
    ev = []
    for r in d.itertuples():
        ev += [(r.entry, 1), (r.exit, -1)]
    ev.sort()
    c = mx = 0
    area = span = 0.0
    prev = None
    for t, x in ev:
        if prev is not None and c > 0:
            dt = (t - prev).total_seconds()
            area += c * dt
            span += dt
        c += x
        mx = max(mx, c)
        prev = t
    return (area / span if span else 0.0), mx


def _bal_at_dd(d: pd.DataFrame, target: float) -> float:
    """Risk oranını maks. düşüş `target`'a eşitleyecek şekilde ayarla ve son
    bakiyeyi döndür. OLAY TABANLI (scripts/equity.py) — eski sıralı bileşik
    eş-zamanlı pozisyonda bakiyeyi kat kat fazla gösteriyordu."""
    from equity import event_equity, risk_for_dd
    return event_equity(d, risk_for_dd(d, target))["final"]


def stats(d: pd.DataFrame) -> dict:
    from equity import event_equity, required_leverage
    isk = d.entry < SPLIT
    _e = event_equity(d, 0.01)
    bal = _e["final"]
    c = _e["curve"].bal if len(_e["curve"]) else pd.Series([10000.0])
    _lev_avg, _lev_max = required_leverage(d, 0.01)
    conc_avg, conc_max = _concurrency(d)
    dd = abs((c / c.cummax() - 1).min()) * 100
    return dict(n=len(d), is_r=d[isk].r.sum(), oos_r=d[~isk].r.sum(),
                r=d.r.sum(), wr=100 * (d.r > 0).mean(), bal=bal, dd=dd,
                bal_norm=_bal_at_dd(d, DD_TARGET),
                lev_avg=_lev_avg, lev_max=_lev_max,
                conc=conc_avg, cmax=conc_max)


def show(name: str, m: dict, base=None) -> None:
    d = ""
    ok = ""
    if base:
        d = " (TOP %+.1f)" % (m["r"] - base["r"])
        # KABUL KRITERI = RISKE-NORMALIZE KIYAS.
        # Eski kriter ("bakiye orani >= dusus orani") YANLISTI: bilesik getiri
        # superlineer buyudugu icin neredeyse her zaman saglaniyordu ve 2026-08
        # kosusunda es-zamanliligi hatali sekilde KABUL gosterdi. Dogrusu:
        # her iki senaryoyu AYNI maksimum dususe ayarlayip bakiyeleri
        # karsilastirmak. Es-zamanlilik gercek edge katiyorsa, ayni dususte
        # daha yuksek bakiye vermeli.
        better = m["is_r"] > base["is_r"] and m["oos_r"] > base["oos_r"]
        gain = m["bal_norm"] / base["bal_norm"] - 1
        ok = ("  <<< KABUL (esit riskte %+.1f%%)" % (100 * gain)
              if (better and gain > 0)
              else "  ELENDI (esit riskte %+.1f%%)" % (100 * gain))
    print("%-14s N=%3d IS=%+6.1f OOS=%+6.1f TOP=%+6.1f%s WR=%4.1f%% "
          "bakiye=%s$ maxDD=%%%.1f  esit-riskte=%s$  es-zaman ort %.2f "
          "tepe %d  kaldirac ort %.1fx tepe %.1fx%s"
          % (name, m["n"], m["is_r"], m["oos_r"], m["r"], d, m["wr"],
             format(m["bal"], ",.0f").replace(",", "."), m["dd"],
             format(m["bal_norm"], ",.0f").replace(",", "."),
             m["conc"], m["cmax"], m["lev_avg"], m["lev_max"], ok),
          flush=True)


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
