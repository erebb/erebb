# -*- coding: utf-8 -*-
"""
ÇIKIŞ KURALI LABORATUVARI — motora DOKUNMADAN çıkış mekanizması denemek
========================================================================
Motorun kaynağı okunur, BELLEKTE yamanır ve sys.modules'e yamalı sürüm
enjekte edilir; gui bu sürümü import eder. Diskteki xauusd_fvg_engine_v10.py,
gui.py ve config/default.json DEĞİŞMEZ. Deney bitince ortada iz kalmaz.

Neden böyle: canlı sistemin kodu, kabul edilmemiş mekanizmaların
parametreleriyle kirlenmemeli. Kabul edilen bir mekanizma olursa asıl koda
o zaman, bilinçli olarak eklenir.

Aileler
-------
  belock  T,L   kâr T·R'ye ulaşınca SL'i L·R seviyesine taşı
                L=0 klasik breakeven · L=-0.5 kısmi sıkılaştırma
                · L=+0.5 kâr kilitle
  maebe   A     A·R ALEYHE gidince "güvenme" işaretle; fiyat girişe
                dönerse başabaşta kapat
  maecut  A     A·R aleyhe gidince doğrudan kes (yarım stop)

Kural: IS (<2025-01-11) ve OOS'ta BİRLİKTE iyileşmeyen aday elenir.
Her koşu önce KONTROL yapar (kural kapalı → mevcut sistemi birebir üretmeli);
kontrol geçmezse sonuçlar basılmaz.

DİKKAT — belock ailesi motorun KENDİ breakeven bloğunun yerine geçer. Yani
threevol'ün preset'indeki "1:2be" (BE@1.0R) davranışı bu ailede LAB'ın
tetik/kilit değerleriyle ezilir. maebe/maecut ailelerinde böyle bir ezme
yoktur; onlar mevcut BE bloğunun önüne eklenir.

DOĞRULAMA (2026-08): kaldırılan be_lock_sweep.py'nin ölçtüğü
tetik 1.0R / kilit −0.5R sonucu bu laboratuvarla yeniden üretildi —
+88.7R (eski: strateji toplamları +88.8R, fark yuvarlamadan).
Kontrol koşusu TOP=+134.4R'yi birebir verdi.

Kullanım:
    python3 scripts/exit_rule_lab.py belock 1.0,-0.5 2.0,-0.75
    python3 scripts/exit_rule_lab.py maebe  0.5 0.75
    python3 scripts/exit_rule_lab.py maecut 0.5
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "xauusd_fvg_engine_v10.py"
MODNAME = "xauusd_fvg_engine_v10"
SPLIT = pd.Timestamp("2025-01-11")
STRATS = ["fvg", "harmonic", "threevol", "fib"]

# Bilinen referans (config/default.json preset'leri, 5 yıl, komisyon dahil)
BASE_TOP = 134.4

# ── çıpa: motorun mevcut breakeven bloğu (birebir) ─────────────────────────
ANCHOR_BE = """            if self.breakeven_at_R is not None and t.sl != entry:"""

# belock: BE bloğunu keyfi tetik/kilit alan sürümle değiştir
PATCH_BELOCK = """            if _LAB_BE_TRIG > 0:
                be_lvl  = (entry + _LAB_BE_TRIG * R if d == 'bull'
                           else entry - _LAB_BE_TRIG * R)
                reached = (H[idx] >= be_lvl) if d == 'bull' else (L[idx] <= be_lvl)
                lock    = (entry + _LAB_BE_LOCK * R if d == 'bull'
                           else entry - _LAB_BE_LOCK * R)
                new_sl  = round(lock, 2)
                improves = (new_sl > t.sl) if d == 'bull' else (new_sl < t.sl)
                if reached and improves:
                    t.sl = new_sl
                    if (L[idx] <= t.sl) if d == 'bull' else (H[idx] >= t.sl):
                        ep    = t.sl
                        mult  = ((ep - entry) if d == 'bull'
                                 else (entry - ep)) / (R + 1e-10)
                        t.exit_price = ep
                        cost  = self._trade_cost(t)
                        dlr   = mult * t.risk_dollar * rem_frac - cost
                        total = t.realized_pnl + dlr
                        t.exit_time = TM[idx]
                        t.result = ('WIN' if total > 0.01 else
                                    ('BE' if abs(total) <= 0.01 else 'LOSS'))
                        t.pnl_dollar = round(total, 2)
                        t.exit_reason = 'be'
                        return True, partial + dlr
"""

# maebe / maecut: BE bloğunun ÖNÜNE eklenir (TP/SL kontrolünden sonra)
PATCH_MAE = """            if _LAB_MAE_ARM > 0:
                adv = ((entry - float(L[idx])) if d == 'bull'
                       else (float(H[idx]) - entry)) / (R + 1e-10)
                if getattr(t, '_lab_armed', False):
                    if (H[idx] >= entry) if d == 'bull' else (L[idx] <= entry):
                        t.exit_price = entry
                        cost  = self._trade_cost(t)
                        total = t.realized_pnl - cost
                        t.exit_time = TM[idx]
                        t.result = ('WIN' if total > 0.01 else
                                    ('BE' if abs(total) <= 0.01 else 'LOSS'))
                        t.pnl_dollar = round(total, 2)
                        t.exit_reason = 'maebe'
                        return True, partial - cost
                if adv >= _LAB_MAE_ARM:
                    if _LAB_MAE_MODE == 'cut':
                        ep   = (entry - _LAB_MAE_ARM * R if d == 'bull'
                                else entry + _LAB_MAE_ARM * R)
                        t.exit_price = ep
                        cost  = self._trade_cost(t)
                        dlr   = -_LAB_MAE_ARM * t.risk_dollar * rem_frac - cost
                        total = t.realized_pnl + dlr
                        t.exit_time = TM[idx]
                        t.result = ('WIN' if total > 0.01 else
                                    ('BE' if abs(total) <= 0.01 else 'LOSS'))
                        t.pnl_dollar = round(total, 2)
                        t.exit_reason = 'maecut'
                        return True, partial + dlr
                    t._lab_armed = True

"""


def load_patched(trig: float = 0.0, lock: float = 0.0,
                 arm: float = 0.0, mode: str = "be") -> None:
    """Yamalı motoru sys.modules'e koy. Diske hiçbir şey yazılmaz."""
    src = SRC.read_text(encoding="utf-8")
    if ANCHOR_BE not in src:
        raise SystemExit("çıpa bulunamadı — motorun BE bloğu değişmiş, "
                         "scripts/exit_rule_lab.py güncellenmeli")
    if trig > 0:                       # belock: BE bloğunun yerine geç
        head, _sep, tail = src.partition(ANCHOR_BE)
        # orijinal bloğu atla (bir sonraki yorum başlığına kadar)
        cut = tail.index("            # ── TAKİP EDEN STOP")
        src = head + PATCH_BELOCK + tail[cut:]
    if arm > 0:                        # mae: BE bloğunun önüne ekle
        src = src.replace(ANCHOR_BE, PATCH_MAE + ANCHOR_BE, 1)
    src = ("_LAB_BE_TRIG = %r\n_LAB_BE_LOCK = %r\n"
           "_LAB_MAE_ARM = %r\n_LAB_MAE_MODE = %r\n"
           % (float(trig), float(lock), float(arm), mode)) + src

    for m in list(sys.modules):
        if m in (MODNAME, "gui", "config"):
            del sys.modules[m]
    mod = types.ModuleType(MODNAME)
    mod.__file__ = str(SRC)
    sys.modules[MODNAME] = mod
    exec(compile(src, str(SRC), "exec"), mod.__dict__)


def run(**kw) -> pd.DataFrame:
    load_patched(**kw)
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
    return pd.DataFrame(rows)


def line(name: str, d: pd.DataFrame, base=None) -> str:
    isk = d.entry < SPLIT
    i, o = d[isk].r.sum(), d[~isk].r.sum()
    bal = 10000.0
    for x in d.sort_values("exit").r:
        bal *= (1 + 0.01 * x)
    delta = ""
    ok = ""
    if base is not None:
        delta = " (IS %+.1f / OOS %+.1f / TOP %+.1f)" % (
            i - base[0], o - base[1], i + o - base[0] - base[1])
        ok = "  <<< KABUL" if (i > base[0] and o > base[1]) else ""
    return ("%-26s N=%3d IS=%+6.1f OOS=%+6.1f TOP=%+6.1f WR=%4.1f%% "
            "bakiye=%s$%s%s\n%28scikislar: %s"
            % (name, len(d), i, o, i + o, 100 * (d.r > 0).mean(),
               format(bal, ",.0f").replace(",", "."), delta, ok, "",
               d.reason.value_counts().to_dict()))


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        return
    fam, args = sys.argv[1], sys.argv[2:]

    print("KONTROL — kural kapalı, mevcut sistemi birebir üretmeli", flush=True)
    b = run()
    bi, bo = b[b.entry < SPLIT].r.sum(), b[b.entry >= SPLIT].r.sum()
    print("  " + line("referans", b), flush=True)
    if abs(bi + bo - BASE_TOP) > 0.5:
        print("  !! KONTROL BASARISIZ (beklenen TOP=%+.1f) — sonuclar "
              "guvenilmez, cikiliyor" % BASE_TOP)
        return
    print("  -> kontrol GECTI\n", flush=True)

    for a in args:
        if fam == "belock":
            t, l = (float(x) for x in a.split(","))
            print("  " + line("tetik %.2f kilit %+.2f" % (t, l),
                              run(trig=t, lock=l), (bi, bo)), flush=True)
        elif fam in ("maebe", "maecut"):
            v = float(a)
            print("  " + line("%s ARM %.2f" % (fam, v),
                              run(arm=v, mode="cut" if fam == "maecut" else "be"),
                              (bi, bo)), flush=True)
        else:
            print("bilinmeyen aile:", fam)
            return
    print("BITTI")


if __name__ == "__main__":
    main()
