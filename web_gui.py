#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_gui.py — XAUUSD FVG System, tarayıcı arayüzü
=================================================
Çalıştır:  python3 web_gui.py            → http://127.0.0.1:8770
           python3 web_gui.py --port 9000 --host 0.0.0.0

BAĞIMLILIK YOK. Yalnız Python standart kütüphanesi (http.server) kullanılır;
Flask/FastAPI gerekmez. Terminal GUI (gui.py) ile AYNI çekirdeği çağırır —
`gui._run_strategy` ve `config` — yani iki arayüz asla ayrışmaz.

Yapabildikleri
  • Sistem durumu: profil, broker, risk, maliyetler, aktif stratejiler
  • Backtest çalıştır (arka planda), canlı ilerleme, sonuç tablosu
  • Ay ay / yıl yıl PnL tablosu (olay tabanlı bileşik)
  • Profil değiştir (swing ↔ scalp) — broker kilidi burada da uygulanır
  • reports/ altındaki HTML raporları listele ve aç

GÜVENLİK
  Varsayılan olarak YALNIZ 127.0.0.1'e bağlanır. --host 0.0.0.0 verirseniz
  arayüz ağa açılır; kimlik doğrulama YOKTUR, config değiştirebilir ve
  backtest başlatabilir. Güvenilmeyen ağda açmayın.
  Canlı emir gönderme bu arayüzde YOKTUR — bilinçli olarak eklenmedi.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import threading
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.chdir(ROOT)

STRATS = ["fvg", "harmonic", "threevol", "fib"]
SPLIT = "2025-01-11"

# ── arka plan işi (aynı anda tek backtest) ──────────────────────────────
JOB = {"state": "idle", "log": [], "result": None, "started": None}
JOB_LOCK = threading.Lock()


def log(msg: str) -> None:
    with JOB_LOCK:
        JOB["log"].append("%s  %s" % (datetime.now().strftime("%H:%M:%S"), msg))
        del JOB["log"][:-200]


def run_backtest() -> None:
    """Tüm aktif stratejileri koş, portföy defterini ve özeti üret."""
    import pandas as pd
    try:
        from config import get_config
        from equity import event_equity
        import gui

        cfg = get_config()
        rows, per = [], []
        for s in STRATS:
            if not cfg.get(s, "enabled", default=True):
                log("%s — kapalı, atlandı" % s)
                continue
            log("%s koşuluyor…" % s)
            r = gui._run_strategy(s, keep_trades=True)[0]
            n = 0
            for t in r.get("_trades", []):
                if t.exit_time is None or t.risk_dollar <= 0:
                    continue
                e = pd.Timestamp(str(t.signal.entry_time)[:19])
                x = pd.Timestamp(str(t.exit_time)[:19])
                rows.append(dict(s=s, entry=e, exit=x,
                                 r=t.pnl_dollar / t.risk_dollar,
                                 reason=getattr(t, "exit_reason", "")))
                n += 1
            sub = [q for q in rows if q["s"] == s]
            rr = sum(q["r"] for q in sub)
            per.append(dict(strateji=s, islem=n, R=round(rr, 1),
                            wr=round(100 * sum(1 for q in sub if q["r"] > 0)
                                     / max(n, 1), 1)))
            log("%s bitti — %d işlem, %+.1fR" % (s, n, rr))

        d = pd.DataFrame(rows).sort_values("exit").reset_index(drop=True)
        if d.empty:
            raise RuntimeError("hiç işlem üretilmedi")
        e = event_equity(d, float(cfg.get("risk", "risk_fraction",
                                          default=0.01)))
        d["pnl"] = e["pnl"]
        d["ym"] = d["exit"].dt.to_period("M").astype(str)
        d["yr"] = d["exit"].dt.year
        isk = d.entry < pd.Timestamp(SPLIT)
        gw = d[d.r > 0].r.sum()
        gl = -d[d.r <= 0].r.sum()

        aylik = (d.groupby("ym")
                  .agg(islem=("r", "size"), R=("r", "sum"), pnl=("pnl", "sum"))
                  .round(1).reset_index().to_dict("records"))
        yillik = (d.groupby("yr")
                   .agg(islem=("r", "size"), R=("r", "sum"), pnl=("pnl", "sum"))
                   .round(1).reset_index().to_dict("records"))
        with JOB_LOCK:
            JOB["result"] = dict(
                islem=len(d), R=round(d.r.sum(), 1),
                IS=round(d[isk].r.sum(), 1), OOS=round(d[~isk].r.sum(), 1),
                wr=round(100 * (d.r > 0).mean(), 1),
                pf=round(gw / gl, 2) if gl else None,
                bakiye=round(e["final"]), dd=round(e["dd"], 1),
                strateji=per, aylik=aylik, yillik=yillik)
        log("TAMAM — %d işlem, %+.1fR, bakiye %.0f$, düşüş %%%.1f"
            % (len(d), d.r.sum(), e["final"], e["dd"]))
    except Exception as ex:
        log("HATA: %s" % ex)
        log(traceback.format_exc().splitlines()[-1])
    finally:
        with JOB_LOCK:
            JOB["state"] = "idle"


def start_job() -> tuple:
    with JOB_LOCK:
        if JOB["state"] == "running":
            return False, "zaten çalışıyor"
        JOB.update(state="running", log=[], result=None,
                   started=datetime.now().strftime("%H:%M:%S"))
    threading.Thread(target=run_backtest, daemon=True).start()
    return True, "başlatıldı"


# ── durum ───────────────────────────────────────────────────────────────

def snapshot() -> dict:
    from config import get_config
    import gui
    cfg = get_config()
    prof = str(cfg.get("profile", default="swing") or "swing")
    broker = str(cfg.get("live", "broker", default="bingx"))
    strat = []
    for s in STRATS:
        strat.append(dict(
            ad=s,
            acik=bool(cfg.get(s, "enabled", default=True)),
            rr=str(gui._profile_get(cfg, s, "rr", "?")),
            swing=bool(gui._profile_get(cfg, s, "swing_stop", True)),
            teb=gui._profile_get(cfg, s, "time_exit_bars", None),
            bias=str(cfg.get(s, "bias", default="none")),
        ))
    costs = cfg.get("costs", default={}) or {}
    return dict(
        profil=prof, broker=broker,
        catisma=gui._profile_broker_conflict(cfg),
        risk=cfg.get("risk", "risk_fraction", default=0.01),
        sermaye=cfg.get("backtest", "initial_capital", default=10000),
        dry_run=bool(cfg.get("live", "dry_run", default=True)),
        costs=costs, stratejiler=strat,
        raporlar=sorted(p.name for p in (ROOT / "reports").glob("*.html")),
        is_calisiyor=(JOB["state"] == "running"))


def set_profile(name: str) -> dict:
    from config import get_config
    import gui
    if name not in ("swing", "scalp"):
        return dict(ok=False, mesaj="bilinmeyen profil")
    cfg = get_config()
    cfg.set("profile", name)
    cfg.save()
    return dict(ok=True, mesaj="profil → %s" % name,
                uyari=gui._profile_broker_conflict(cfg))


# ── HTTP ────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = "XAUUSD-WebGUI"

    def log_message(self, *a):        # konsolu kirletme
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        u = urlparse(self.path)
        p, q = u.path, parse_qs(u.query)
        try:
            if p == "/":
                return self._send(200, PAGE.encode("utf-8"),
                                  "text/html; charset=utf-8")
            if p == "/api/durum":
                return self._json(snapshot())
            if p == "/api/log":
                with JOB_LOCK:
                    return self._json(dict(state=JOB["state"],
                                           log=list(JOB["log"]),
                                           result=JOB["result"]))
            if p == "/rapor":
                name = (q.get("f") or [""])[0]
                # yol kacisi engellenir: yalnız reports/ altındaki .html
                f = (ROOT / "reports" / name).resolve()
                if (f.suffix != ".html"
                        or f.parent != (ROOT / "reports").resolve()
                        or not f.exists()):
                    return self._send(404, b"bulunamadi", "text/plain")
                return self._send(200, f.read_bytes(),
                                  "text/html; charset=utf-8")
            return self._send(404, b"yok", "text/plain")
        except Exception as ex:
            return self._json(dict(hata=str(ex)), 500)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        try:
            if u.path == "/api/backtest":
                ok, msg = start_job()
                return self._json(dict(ok=ok, mesaj=msg))
            if u.path == "/api/profil":
                return self._json(set_profile(str(body.get("ad", ""))))
            return self._send(404, b"yok", "text/plain")
        except Exception as ex:
            return self._json(dict(hata=str(ex)), 500)


PAGE = r"""<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>XAUUSD FVG — Kontrol Paneli</title>
<style>
:root{--bg:#fbfaf8;--panel:#fff;--ink:#1c1a17;--dim:#6f6963;--line:#e7e2db;
 --gold:#9a7c18;--pos:#1e7d52;--neg:#c0384a;--shade:#f4f1ea}
@media(prefers-color-scheme:dark){:root{--bg:#0f1217;--panel:#171b22;
 --ink:#e9e6e1;--dim:#8b9199;--line:#252b34;--gold:#d8b23f;--pos:#3fbd80;
 --neg:#e8607a;--shade:#1b2029}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1060px;margin:0 auto;padding:32px 20px 70px;
 display:flex;flex-direction:column;gap:26px}
header{border-bottom:2px solid var(--gold);padding-bottom:14px;
 display:flex;justify-content:space-between;align-items:baseline;gap:16px;
 flex-wrap:wrap}
h1{margin:0;font:600 25px/1.2 Georgia,serif}
h2{margin:0 0 10px;font:600 16px/1.3 Georgia,serif;padding-bottom:7px;
 border-bottom:1px solid var(--line)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
 gap:1px;background:var(--line);border:1px solid var(--line);border-radius:6px;
 overflow:hidden}
.cell{background:var(--panel);padding:12px 14px}
.cell .k{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;
 color:var(--dim);display:block;margin-bottom:4px}
.cell .v{font:600 17px/1.2 ui-monospace,Menlo,monospace;
 font-variant-numeric:tabular-nums}
button{font:600 13px/1 inherit;padding:9px 16px;border-radius:6px;
 border:1px solid var(--gold);background:var(--gold);color:#fff;cursor:pointer}
button.ghost{background:transparent;color:var(--gold)}
button:disabled{opacity:.45;cursor:not-allowed}
.row{display:flex;gap:9px;flex-wrap:wrap;align-items:center}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;
 background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:460px}
th,td{padding:6px 11px;text-align:left;border-bottom:1px solid var(--line);
 white-space:nowrap}
thead th{background:var(--panel);color:var(--dim);font-size:10.5px;
 letter-spacing:.05em;text-transform:uppercase;border-bottom:1px solid var(--gold)}
td.num,th.num{text-align:right;font-family:ui-monospace,Menlo,monospace;
 font-variant-numeric:tabular-nums}
.pos{color:var(--pos)}.neg{color:var(--neg)}
pre{background:var(--panel);border:1px solid var(--line);border-radius:6px;
 padding:11px;font-size:12px;max-height:230px;overflow:auto;margin:0}
.note{color:var(--dim);font-size:12.5px}
.warn{background:#c0384a18;border-left:3px solid var(--neg);
 padding:10px 13px;border-radius:0 4px 4px 0;font-size:13px}
.pill{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;
 border:1px solid var(--line);background:var(--shade);color:var(--dim)}
a{color:var(--gold)}
</style>
<div class="wrap">
<header>
  <h1>XAUUSD FVG — Kontrol Paneli</h1>
  <span class="note" id="ust"></span>
</header>

<section>
  <h2>Durum</h2>
  <div class="grid" id="durum"></div>
  <div id="catisma"></div>
  <div class="row" style="margin-top:12px">
    <button id="btnBt">Backtest çalıştır</button>
    <button class="ghost" id="btnSwing">Profil: swing</button>
    <button class="ghost" id="btnScalp">Profil: scalp</button>
    <span class="note" id="msg"></span>
  </div>
</section>

<section>
  <h2>Stratejiler</h2>
  <div class="scroll"><table id="tblStrat"></table></div>
</section>

<section>
  <h2>Çalışma günlüğü</h2>
  <pre id="log">—</pre>
</section>

<section id="secSonuc" style="display:none">
  <h2>Sonuç</h2>
  <div class="grid" id="ozet"></div>
  <div style="margin-top:14px" class="scroll"><table id="tblYil"></table></div>
  <div style="margin-top:14px" class="scroll"><table id="tblAy"></table></div>
</section>

<section>
  <h2>Raporlar</h2>
  <div id="raporlar" class="note">—</div>
</section>
</div>

<script>
const $=id=>document.getElementById(id);
const f0=v=>Math.round(v).toLocaleString('tr-TR');
const sgn=v=>(v>0?'pos':v<0?'neg':'');
function cell(k,v,c){return `<div class="cell"><span class="k">${k}</span>
  <span class="v ${c||''}">${v}</span></div>`;}
function tbl(el,head,rows){
  el.innerHTML='<thead><tr>'+head.map(h=>`<th class="${h[1]||''}">${h[0]}</th>`).join('')
   +'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(c=>
     `<td class="${c[1]||''}">${c[0]}</td>`).join('')+'</tr>').join('')+'</tbody>';
}
async function durum(){
  const d=await (await fetch('/api/durum')).json();
  $('ust').textContent=`profil ${d.profil} · broker ${d.broker} · risk %${(d.risk*100).toFixed(2)}`;
  $('durum').innerHTML=
    cell('Profil',d.profil)+cell('Broker',d.broker)+
    cell('Risk / işlem','%'+(d.risk*100).toFixed(2))+
    cell('Sermaye',f0(d.sermaye)+' $')+
    cell('Dry-run',d.dry_run?'açık':'KAPALI',d.dry_run?'':'neg')+
    cell('Komisyon','%'+d.costs.commission_pct+' / %'+d.costs.maker_pct)+
    cell('Spread',d.costs.spread_usd+' $');
  $('catisma').innerHTML=d.catisma?`<div class="warn">${d.catisma}</div>`:'';
  tbl($('tblStrat'),[['Strateji'],['Durum'],['RR','num'],['Stop'],['Zaman çıkışı','num'],['Bias']],
    d.stratejiler.map(s=>[[s.ad],[s.acik?'açık':'<span class="pill">kapalı</span>'],
      [s.rr,'num'],[s.swing?'1H swing':'POI'],
      [s.teb?(s.teb*5/60)+' saat':'—','num'],[s.bias]]));
  $('raporlar').innerHTML=d.raporlar.length
    ? d.raporlar.map(r=>`<a href="/rapor?f=${encodeURIComponent(r)}" target="_blank">${r}</a>`).join(' · ')
    : 'reports/ altında HTML rapor yok';
  $('btnBt').disabled=d.is_calisiyor;
}
async function gunluk(){
  const d=await (await fetch('/api/log')).json();
  $('log').textContent=d.log.length?d.log.join('\n'):'—';
  $('log').scrollTop=$('log').scrollHeight;
  $('btnBt').disabled=(d.state==='running');
  if(d.result){
    const r=d.result; $('secSonuc').style.display='';
    $('ozet').innerHTML=cell('İşlem',r.islem)+cell('Toplam R',(r.R>0?'+':'')+r.R,sgn(r.R))
      +cell('IS / OOS',r.IS+' / '+r.OOS)+cell('Kazanma','%'+r.wr)
      +cell('Profit factor',r.pf??'—')+cell('Bakiye',f0(r.bakiye)+' $')
      +cell('Maks. düşüş','%'+r.dd,'neg');
    tbl($('tblYil'),[['Yıl'],['İşlem','num'],['R','num'],['PnL','num']],
      r.yillik.map(x=>[[x.yr],[x.islem,'num'],
        [`<span class="${sgn(x.R)}">${x.R>0?'+':''}${x.R}</span>`,'num'],
        [`<span class="${sgn(x.pnl)}">${x.pnl>0?'+':''}${f0(x.pnl)} $</span>`,'num']]));
    tbl($('tblAy'),[['Ay'],['İşlem','num'],['R','num'],['PnL','num']],
      r.aylik.map(x=>[[x.ym],[x.islem,'num'],
        [`<span class="${sgn(x.R)}">${x.R>0?'+':''}${x.R}</span>`,'num'],
        [`<span class="${sgn(x.pnl)}">${x.pnl>0?'+':''}${f0(x.pnl)} $</span>`,'num']]));
  }
}
$('btnBt').onclick=async()=>{
  $('msg').textContent='';
  const r=await (await fetch('/api/backtest',{method:'POST'})).json();
  $('msg').textContent=r.mesaj||''; durum();
};
async function setProfil(ad){
  const r=await (await fetch('/api/profil',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({ad})})).json();
  $('msg').textContent=(r.mesaj||'')+(r.uyari?(' — '+r.uyari):''); durum();
}
$('btnSwing').onclick=()=>setProfil('swing');
$('btnScalp').onclick=()=>setProfil('scalp');
durum(); gunluk(); setInterval(gunluk,1500); setInterval(durum,6000);
</script>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="XAUUSD FVG web arayüzü")
    ap.add_argument("--host", default="127.0.0.1",
                    help="varsayılan 127.0.0.1 (yalnız bu makine). "
                         "0.0.0.0 ağa açar — kimlik doğrulama YOKTUR.")
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args()
    if a.host not in ("127.0.0.1", "localhost"):
        print("UYARI: arayüz %s adresine açılıyor. Kimlik doğrulama yok; "
              "config değiştirilebilir ve backtest başlatılabilir." % a.host)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print("XAUUSD FVG web arayüzü  →  http://%s:%d" % (a.host, a.port))
    print("Durdurmak için Ctrl+C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nkapatıldı")


if __name__ == "__main__":
    main()
