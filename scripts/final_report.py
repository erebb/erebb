# -*- coding: utf-8 -*-
"""
NİHAİ SİSTEM DOKÜMANI — tüm düzeltmeler, testler ve işlem adli analizi
======================================================================
Tek bir HTML dokümanda:
  1. Yönetici özeti + sistemin bugünkü hali
  2. Bulunan ve düzeltilen HATALAR (kronolojik, önce/sonra rakamlarıyla)
  3. KABUL EDİLEN mekanizmalar (IS/OOS kanıtıyla)
  4. REDDEDİLEN mekanizmalar (neden reddedildiği, rakamlarıyla)
  5. İŞLEM ADLİ ANALİZİ — TP olanlar neden TP oldu, stop olanlar neden stop oldu:
     giriş anındaki EMA dizilimi, MACD (5M/15M/1H/4H/1D), HACİM, ATR, Bollinger,
     trend uyumu, MFE/MAE, süre — TP ve SL grupları yan yana
  6. Volatilite ve trend rejim analizi
  7. Aylık / yıllık performans + grafikler
  8. Canlıya geçiş notları

Kullanım:  python3 scripts/final_report.py
Çıktı:     reports/NIHAI_RAPOR.html   (grafikler gömülü, tek dosya, UTF-8)
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "reports"
SPLIT = pd.Timestamp("2025-01-11")          # IS / OOS ayrım noktası (%70)


# ═══════════════════════ bağlam (hepsi CAUSAL) ══════════════════════════════

def build_context(df_5m, df_1h):
    """Giriş anında BİLİNEN göstergeler. Her seri 'bilinme anı' indeksiyle
    kurulur → asof() ile bakmak lookahead içermez."""
    ctx = {}

    def pack(df, tag, shift):
        c, h, l = df["Close"], df["High"], df["Low"]
        idx = df.index + shift
        ef = c.ewm(span=12, adjust=False).mean()
        es = c.ewm(span=26, adjust=False).mean()
        macd = ef - es
        sig = macd.ewm(span=9, adjust=False).mean()
        e9 = c.ewm(span=9, adjust=False).mean()
        e21 = c.ewm(span=21, adjust=False).mean()
        e50 = c.ewm(span=50, adjust=False).mean()
        e200 = c.ewm(span=200, adjust=False).mean()
        tr = pd.concat([h - l, (h - c.shift()).abs(),
                        (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        d_ = c.diff()
        up = d_.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
        dn = (-d_.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
        rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
        ma, sd = c.rolling(20).mean(), c.rolling(20).std()
        for k, v in [("macd", macd / c * 100), ("hist", (macd - sig) / c * 100),
                     ("rsi", rsi), ("atrp", atr / c * 100),
                     ("bbw", 4 * sd / ma * 100),
                     ("stack", pd.Series(np.where(e9 > e21, np.where(e21 > e50, 2, 1),
                                                  np.where(e21 < e50, -2, -1)),
                                         index=df.index)),
                     ("above200", pd.Series(np.where(c > e200, 1, 0), index=df.index))]:
            s = v.copy(); s.index = idx
            ctx[f"{tag}_{k}"] = s
        if "Volume" in df.columns:
            vol = df["Volume"]
            vr = vol / vol.rolling(50).median()
            s = vr.copy(); s.index = idx
            ctx[f"{tag}_volr"] = s
            cvd = (np.sign(c - df["Open"]) * vol).rolling(20).sum()
            s2 = cvd.copy(); s2.index = idx
            ctx[f"{tag}_cvd20"] = s2

    pack(df_5m, "m5", pd.Timedelta(minutes=5))
    pack(df_1h, "h1", pd.Timedelta(hours=1))
    df15 = df_5m.resample("15min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last",
         "Volume": "sum"}).dropna(subset=["Close"])
    pack(df15, "m15", pd.Timedelta(minutes=15))
    df4 = df_1h.resample("4h", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last",
         "Volume": "sum"}).dropna(subset=["Close"])
    pack(df4, "h4", pd.Timedelta(hours=4))
    dfd = df_1h.resample("1D").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last",
         "Volume": "sum"}).dropna(subset=["Close"])
    pack(dfd, "d1", pd.Timedelta(days=1))
    return ctx


def at(s, ts, d=np.nan):
    if s is None or len(s) == 0:
        return d
    v = s.asof(ts)
    try:
        return float(v)
    except Exception:
        return d


def build_ledger(ctx):
    from gui import _run_strategy
    from xauusd_fvg_engine_v10 import to_naive
    rows = []
    for s in ["fvg", "harmonic", "threevol"]:
        r = _run_strategy(s, keep_trades=True)[0]
        print(f"  {s}: N={r['total']} PnL={r['pnl']:+.1f} PF={r['pf']:.2f}", flush=True)
        for t in r.get("_trades", []):
            if t.exit_time is None or t.risk_dollar <= 0:
                continue
            ts = to_naive(t.signal.entry_time)
            xs = to_naive(t.exit_time)
            rec = dict(s=s, entry=ts, exit=xs, dir=t.signal.direction,
                       r=t.pnl_dollar / t.risk_dollar, px=t.entry_price,
                       sl=t.sl, tp=t.tp, stop=t.risk,
                       res=t.result, reason=getattr(t, "exit_reason", ""),
                       mfe=getattr(t, "mfe_r", np.nan),
                       mae=getattr(t, "mae_r", np.nan),
                       dur_h=(xs - ts).total_seconds() / 3600,
                       hour=ts.hour, dow=ts.weekday())
            for k, v in ctx.items():
                rec[k] = at(v, ts)
            rows.append(rec)
    d = pd.DataFrame(rows).sort_values("exit").reset_index(drop=True)
    d["kazanan"] = d.r > 0
    return d


# ═══════════════════════════ görsel yardımcılar ═════════════════════════════

def b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight",
                facecolor="#12161c")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def img(fig, alt=""):
    return f'<img src="data:image/png;base64,{b64(fig)}" alt="{alt}">'


def dark(ax):
    for a in (ax if isinstance(ax, (list, np.ndarray)) else [ax]):
        a.set_facecolor("#12161c")
        a.tick_params(colors="#9fb0c4", labelsize=8)
        for sp in a.spines.values():
            sp.set_color("#2a3542")
        a.grid(alpha=0.15, color="#3a4552")


def tbl(headers, rows, note=""):
    h = "".join(f"<th>{x}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    n = f'<p class="note">{note}</p>' if note else ""
    return (f'<div class="tw"><table><thead><tr>{h}</tr></thead>'
            f"<tbody>{b}</tbody></table></div>{n}")


def cmp_row(label, w, l, fmt="{:+.2f}"):
    """Kazanan vs kaybeden karşılaştırma satırı + ayırt edicilik."""
    if len(w) == 0 or len(l) == 0:
        return None
    mw, ml = w.mean(), l.mean()
    pooled = np.sqrt((w.var() + l.var()) / 2) or 1e-9
    d = (mw - ml) / pooled                      # Cohen's d
    güç = "GÜÇLÜ" if abs(d) >= 0.5 else ("orta" if abs(d) >= 0.25 else "zayıf")
    cls = "p" if d > 0 else "n"
    return [label, fmt.format(mw), fmt.format(ml),
            f'<span class="{cls}">{mw-ml:+.2f}</span>', f"{d:+.2f}", güç]


CSS = """
body{background:#0e1218;color:#dfe6ee;font-family:-apple-system,'Segoe UI',Roboto,sans-serif;
     max-width:1180px;margin:auto;padding:26px;line-height:1.55}
h1{border-bottom:3px solid #3d5a80;padding-bottom:10px;font-size:1.7em}
h2{color:#f5c542;margin-top:2.4em;border-bottom:1px solid #2a3542;padding-bottom:6px}
h3{color:#9fc2e8;margin-top:1.6em}h4{color:#c7d6e8;margin-bottom:4px}
img{max-width:100%;border:1px solid #2a3542;border-radius:5px;margin:10px 0}
table{border-collapse:collapse;font-size:.85em;margin:8px 0;width:100%;
      font-variant-numeric:tabular-nums}
th,td{border:1px solid #2a3542;padding:4px 9px;text-align:right}
th{background:#1a222c;color:#9fc2e8}td:first-child,th:first-child{text-align:left}
.tw{overflow-x:auto}.p{color:#26a69a;font-weight:600}.n{color:#ef5350;font-weight:600}
.note{font-size:.83em;color:#8ea0b5;margin:2px 0 14px}
.kutu{background:#161d26;border-left:4px solid #f5c542;padding:12px 16px;margin:14px 0;
      border-radius:0 5px 5px 0}
.ok{border-left-color:#26a69a}.red{border-left-color:#ef5350}
.big{font-size:1.35em;font-weight:700;color:#26a69a}
.toc{background:#161d26;padding:14px 20px;border-radius:6px;columns:2}
.toc a{color:#7fb3e8;text-decoration:none;display:block;padding:2px 0}
"""


# ═══════════════════════════════ BÖLÜMLER ═══════════════════════════════════

def s_ozet(d, bal, mdd, aypoz):
    W, L = d[d.kazanan], d[~d.kazanan]
    gw, gl = W.r.sum(), -L.r.sum()
    return f"""
<h2 id="s1">1. Yönetici Özeti</h2>
<div class="kutu ok">
<p class="big">10.000$ → {bal:,.0f}$ &nbsp;|&nbsp; yıllık bileşik +%{((bal/10000)**(1/5)-1)*100:.1f}
 &nbsp;|&nbsp; MaxDD %{mdd:.1f}</p>
<p>{len(d)} işlem (5 yıl, {len(d)/5:.0f}/yıl) · WR %{d.kazanan.mean()*100:.1f} ·
PF {gw/gl:.2f} · IS {d[d.entry<SPLIT].r.sum():+.1f}R / OOS {d[d.entry>=SPLIT].r.sum():+.1f}R ·
pozitif ay %{aypoz:.0f}</p>
</div>
<p>Sistem üç <b>bağımsız</b> stratejiden oluşur; hepsi aynı iki ortak kurala tabidir:
günlük SMA200 <b>makro trend uyumu</b> ve <b>swing tabanlı geniş stoplar</b>.
Tüm rakamlar gerçek BingX VIP0 ücretleriyle (taker %0.05 / maker %0.02),
her işlemde sabit %1 risk ve bileşik kasa büyümesiyle hesaplanmıştır.</p>
<div class="kutu">
<b>Bu doküman neyi kanıtlar:</b> sistemin kârlılığı tek bir parametre setinin
şansı değil — 5 yıl (61 ay), dört farklı piyasa rejimi (boğa, ayı, akümülasyon,
şok) ve IS/OOS ayrımıyla test edilmiştir. Aynı derecede önemlisi: <b>denenip
REDDEDİLEN</b> 14 mekanizma da rakamlarıyla belgelenmiştir — sistemin sade
kalması bir tercih değil, ölçümün sonucudur.
</div>"""


def s_hatalar():
    rows = [
        ["Veri ölçeği", "Yüklenen 5y veride tüm OHLC <b>10× şişik</b> (altın 3.326$ yerine 33.264$)",
         "Tüm $-tabanlı eşikler bozuldu; backtest anlamsızdı", "÷10 düzeltildi, örtüşen barla doğrulandı"],
        ["Lookahead (QWE)", "4H blok eşlemesinde saniye/ns birim karışması",
         "Her bara SON 4H bloğun rejimi uygulanıyordu (geleceği görme)",
         "int64 ns normalizasyonu; kesme-değişmezlik testiyle yakalandı"],
        ["Lookahead (bias)", "DailyBiasProvider aynı günün gerçekleşmiş yönünü döndürüyordu",
         "WR yapay olarak %76'ya şişmişti", "Önceki tamamlanmış güne çevrildi + koruma testi"],
        ["Ücret parametresi", "Kripto perp tarifesi (%0.05/%0.02) doğru, ama bir ara %0.01 varsayıldı",
         "Yanlış varsayım altında filtreler/RR yanlış seçildi",
         "BingX VIP0'a sabitlendi; mekanik denetim: işlem başına tam 1 kez, elle hesapla 0.0000$ fark"],
        ["RR (en pahalı)", "Tüm kazananlar <b>tam 2R'de</b> kesiliyordu, 2.5R+ kovası BOŞ",
         "Trendler erken kapatılıyor, kârın yarısı bırakılıyordu",
         "1:5'e çıkarıldı → fvg +52.9R → +101.1R (PF 1.63 → 2.11)"],
        ["Çift risk (yapısal)", "fvg <code>poi_mode='all'</code> zaten PRZ'yi içeriyordu; harmonic de PRZ alıyordu",
         "70 harmonic işleminin <b>68'i (%97)</b> fvg ile aynı zaman/fiyat/sonuç → aynı kuruluma %2 risk",
         "fvg → <code>poi_mode='fvg'</code>: iki gerçekten bağımsız kaynak. MaxDD %19.0 → %10.6"],
        ["Canlı/backtest paritesi", "Live trader'da <code>RiskManager(rr=2.0)</code> sabit kodlanmış",
         "Backtest 1:5, canlı 1:2 kapatacaktı — RR kazancının tamamı canlıda kaybolurdu",
         "RR config'ten okunuyor; min_stop, trend kapısı, swing stop da paritede"],
        ["Performans (O(n²))", "build_mitigation_map + get_active lineer taramalar",
         "5 yıllık veride tek backtest saatlerce sürüyordu (rapor imkânsız)",
         "searchsorted + argmax vektörleştirme; eski mantıkla SIFIR fark kanıtlandı, 240s'ye indi"],
    ]
    return ("<h2 id=\"s2\">2. Bulunan ve Düzeltilen Hatalar</h2>"
            "<p>Kronolojik değil, etki sırasına göre. Her biri ölçümle bulundu, "
            "düzeltme ayrıca doğrulandı.</p>"
            + tbl(["Alan", "Hata", "Etkisi", "Düzeltme + kanıt"], rows))


def s_kabul():
    rows = [
        ["Günlük SMA200 trend kapısı", "Sinyal yönü makro trendle uyuşmalı; ısınmada giriş yok",
         "filtresiz −13.0R (PF 0.98) → <b>+72.1R</b> (PF 1.22)",
         "SMA 100/150/200/250 <b>hepsinde</b> IS+OOS pozitif; her ücret seviyesinde ayakta"],
        ["RR 1:5 (fvg, harmonic)", "Sabit 5R hedef; BE'siz",
         "fvg +52.9R → <b>+101.1R</b>; harmonic +15.0R → <b>+41.4R</b>",
         "1:5–1:7 platosu; 1:5 platonun ORTASI (en sağlam nokta) seçildi"],
        ["RR 1:2be (threevol)", "Momentum scalper'ı farklı RR ister",
         "1:2be +12.5R; 1:3fix'te IS −2.9 ile çürüyor",
         "Tek tip RR uygulamak bu stratejiyi bozuyordu"],
        ["poi_mode ayrımı", "fvg=FVG/OB, harmonic=PRZ → bağımsız kaynaklar",
         "Çift işlem 69 → 8; <b>MaxDD %19.0 → %10.6</b>, R/DD 8.16 → <b>10.93</b>",
         "Aynı pozitif ay oranı (%62), yarı drawdown"],
        ["Swing tabanlı stoplar", "SL son onaylı 1H fractal swing'e genişletilir",
         "Kapatınca +52.9R → +36.7R (PF 1.63 → 1.27)",
         "Ücret_R ∝ 1/stop_mesafesi — dar stop ücreti patlatır"],
        ["EMA-MACD (1H) filtresi", "Sinyal sonrası 1H momentum onayı",
         "Kapatınca 317 işlem ama +29.2R (kâr yarıya, PF 1.63 → 1.13)",
         "harmonic'te kapatınca <b>zarara</b> geçiyor (−7.2R)"],
        ["Blackout 09-11 UTC", "Bu saatlerde giriş yok",
         "Kapatınca +52.9R → +48.0R", "Küçük ama tutarlı katkı"],
        ["threevol min_stop %0.1", "Dar-stop reddi",
         "33 → <b>75 işlem</b>, +10.0R → +12.5R", "Hem daha çok işlem hem daha çok kâr"],
    ]
    return ("<h2 id=\"s3\">3. Kabul Edilen Mekanizmalar</h2>"
            "<p>Kural: bir mekanizma ancak <b>IS ve OOS'ta birlikte</b> pozitifse "
            "sisteme girer; sonra en kârlı varyant seçilir.</p>"
            + tbl(["Mekanizma", "Ne yapar", "Ölçülen etki", "Sağlamlık kanıtı"], rows))


def s_red():
    rows = [
        ["Aylık devre kesici (−4R/−5R)", "Ay içi kayıp limitinde dur",
         "−4R: +148.7R · −5R: <b>+146.2R</b> (temel +155.0)",
         "Kesme yanlılığı: ay içinde durunca toparlanma işlemleri de gider. "
         "Eğri sıçramalı (−3 iyi, −4/−5 kötü, −6 iyi) = gürültü"],
        ["Ardışık kayıp → DUR", "3-5 ardışık kayıptan sonra duraklat",
         "15 varyantın en iyisi +155.1R (fark +0.1); en kötüsü <b>+43.2R</b>",
         "WR %33'te 3 ardışık kayıp olasılığı %30 — normal olay, rejim sinyali değil"],
        ["Ardışık kayıp → KÜÇÜL", "4 ardışık sonrası risk ×0.5",
         "R +163.5 ama <b>IS +90.3 / OOS +73.1</b> (temel OOS +74.4)",
         "Kazancın TAMAMI IS'te; OOS'ta iyileşme YOK → aşırı-uyum imzası"],
        ["ADX rejim kapısı", "Günlük ADX tabanı (15-25)",
         "En iyisi ADX≥20: +127.7R (temel +155.0)",
         "Aylık istatistik (ADX&lt;20 aylar −23.6R) işlem seviyesine ÇEVRİLMEDİ"],
        ["Günlük MACD kapısı", "|MACD%| tabanı (0.3/0.5)",
         "+101.7R / +100.8R (temiz temel +115.9R)",
         "Aynı tuzak: ay ortalaması ≠ işlem anı"],
        ["Takip eden stop (trailing)", "Kâr NR'ye ulaşınca SL sürüklenir",
         "En iyisi 4ATR@2R: +87.0R, pozitif ay %68 (temel +115.9R, %62)",
         "Aylık tutarlılığı artırıyor ama kârı %25 kesiyor — frontier'ı yenmiyor"],
        ["Kısmi TP + runner", "1R/1.5R/2R/3R'de %30-50 kapat",
         "En iyisi +79.2R (düz 1:5'in +101.1R'sine karşı)",
         "Kazananların medyan MFE'si <b>+5.03R</b> — yarısını feda etmek pahalı"],
        ["Confluence (kesişim)", "İki strateji aynı anda onaylayınca işlem/çift boyut",
         "Çakışan: ort <b>+0.553R</b>, WR %27.9 · Çakışmayan: <b>+1.199R</b>, WR %37.7",
         "Kesişim bölgesi KÖTÜ yarı; üstelik o 'kesişim' zaten aynı işlemin kendisiydi"],
        ["Zaman stopu", "N saatte kapat",
         "Kazananlar ort <b>233 saat</b>, kaybedenler 75 saat sürüyor",
         "Erken kapatmak kazananları keser"],
        ["EMA200 altını eleme", "Yalnız 200 üstünde işlem",
         "200 altı işlemler: 40 adet, <b>+10.9R</b> (zayıf ama KÂRLI)",
         "Elemek kaybettirir; zarar aylarının çoğu 200'ün ÜSTÜNDEKİ akümülasyon ayları"],
        ["Filtre gevşetme (işlem↑)", "EMA/blackout kapatarak işlem sayısını artır",
         "fvg: 317 işlem ama +29.2R · harmonic: 214 işlem, <b>−7.2R</b>",
         "Az işlem arıza değil, seçiciliğin ta kendisi"],
        ["BE'li yüksek RR", "1:3be / 1:4be",
         "+53.3R / +52.8R (BE'siz karşılıkları +80.3R / +86.7R)",
         "1R'de başabaşa çekmek runner'ları öldürüyor"],
        ["Limit giriş (düşük ücrette)", "Maker girişle ücret tasarrufu",
         "maker=taker olsaydı market daha iyiydi (+77.9R vs +64.8R)",
         "VIP0'da maker %0.02 &lt; taker %0.05 → limit AVANTAJLI, korundu"],
        ["min_stop_pct %0.6", "Dar-stop reddi (agresif eşik)",
         "Şişik ücret varsayımının koltuk değneğiydi: doğru ücrette +146R → +70R",
         "Gerçek tarifede fvg/harmonic'te gereksiz; yalnız threevol %0.1 kullanıyor"],
    ]
    return ("<h2 id=\"s4\">4. Reddedilen Mekanizmalar</h2>"
            "<div class='kutu red'>Bu tablo raporun en değerli kısmı olabilir: "
            "sistemin sade kalması bir tercih değil, <b>14 mekanizmanın ölçümle "
            "elenmesinin</b> sonucudur. Hiçbiri sezgiyle reddedilmedi.</div>"
            + tbl(["Mekanizma", "Fikir", "Ölçülen sonuç", "Neden reddedildi"], rows))


def s_adli(d):
    """TP olanlar neden TP oldu, stop olanlar neden stop oldu."""
    W, L = d[d.kazanan], d[~d.kazanan]
    h = ['<h2 id="s5">5. İşlem Adli Analizi — TP\'ler ve Stop\'lar</h2>']
    h.append(f"<p>Kazanan <b>{len(W)}</b> · kaybeden <b>{len(L)}</b> işlem. "
             "Aşağıdaki tüm göstergeler <b>giriş anında bilinen</b> değerlerdir "
             "(her seri 'bilinme anı' indeksiyle kuruldu → lookahead yok). "
             "Son sütun <b>Cohen's d</b>: iki grubu ayırt etme gücü "
             "(|d|≥0.5 güçlü, ≥0.25 orta).</p>")

    # ── çıkış nedenleri ──
    rr = []
    for reason, g in d.groupby("reason"):
        rr.append([reason or "(yok)", len(g), f"{g.r.sum():+.1f}",
                   f"{g.r.mean():+.3f}", f"{g.dur_h.mean():.0f} saat"])
    h.append("<h3>5.1 Çıkış nedenleri</h3>")
    h.append(tbl(["Çıkış", "N", "Toplam R", "Ort R", "Ort süre"], rr))

    # ── MFE / MAE ──
    h.append("<h3>5.2 İşlemler ne kadar lehte/aleyhte gitti (MFE / MAE)</h3>")
    mm = [["KAZANANLAR", len(W), f"{W.mfe.mean():+.2f}R", f"{W.mfe.median():+.2f}R",
           f"{W.mfe.max():+.2f}R", f"{W.mae.mean():.2f}R", f"{W.dur_h.mean():.0f} saat"],
          ["KAYBEDENLER", len(L), f"{L.mfe.mean():+.2f}R", f"{L.mfe.median():+.2f}R",
           f"{L.mfe.max():+.2f}R", f"{L.mae.mean():.2f}R", f"{L.dur_h.mean():.0f} saat"]]
    h.append(tbl(["Grup", "N", "MFE ort", "MFE medyan", "MFE max",
                  "MAE ort", "Süre ort"], mm,
                 "MFE = lehe en uzak nokta, MAE = aleyhe en uzak nokta (R cinsi)."))
    buck = []
    for lo, hi in [(0, .3), (.3, .5), (.5, 1), (1, 1.5), (1.5, 2), (2, 3), (3, 99)]:
        g = L[(L.mfe >= lo) & (L.mfe < hi)]
        if len(g):
            buck.append([f"{lo}–{hi if hi < 99 else '+'}R", len(g),
                         f"%{len(g)/len(L)*100:.1f}", f"{g.r.sum():+.1f}R"])
    h.append("<h4>Kaybedenler stop olmadan önce ne kadar kâra geçmişti?</h4>")
    h.append(tbl(["MFE aralığı", "N", "Pay", "Toplam kayıp"], buck,
                 f"Kaybedenlerin %{(L.mfe>=1).mean()*100:.0f}'i +1R'ye, "
                 f"%{(L.mfe>=2).mean()*100:.0f}'i +2R'ye ulaşıp dönmüş. "
                 "Bu, takip eden stop için en güçlü argümandı — ama kazananların "
                 f"medyan MFE'si {W.mfe.median():+.2f}R olduğu için erken kâr alma "
                 "(kısmi TP) net zararlı çıktı; trailing de kârı %25 kesti.")) 

    # ── giriş anı bağlamı: kazanan vs kaybeden ──
    h.append("<h3>5.3 Giriş anındaki piyasa bağlamı — kazananlar vs kaybedenler</h3>")
    grp = [
        ("MACD (momentum)", [
            ("Günlük MACD (%fiyat)", "d1_macd"), ("Günlük MACD histogram", "d1_hist"),
            ("4H MACD (%fiyat)", "h4_macd"), ("1H MACD (%fiyat)", "h1_macd"),
            ("15M MACD (%fiyat)", "m15_macd"), ("5M MACD (%fiyat)", "m5_macd")]),
        ("EMA dizilimi (+2 = 9>21>50)", [
            ("Günlük EMA dizilimi", "d1_stack"), ("4H EMA dizilimi", "h4_stack"),
            ("1H EMA dizilimi", "h1_stack"), ("5M EMA dizilimi", "m5_stack"),
            ("Günlük EMA200 üstü (1/0)", "d1_above200")]),
        ("VOLATİLİTE", [
            ("Günlük ATR (%fiyat)", "d1_atrp"), ("1H ATR (%fiyat)", "h1_atrp"),
            ("5M ATR (%fiyat)", "m5_atrp"), ("Günlük Bollinger genişliği", "d1_bbw"),
            ("1H Bollinger genişliği", "h1_bbw")]),
        ("HACİM", [
            ("5M hacim / 50-bar medyan", "m5_volr"), ("1H hacim / medyan", "h1_volr"),
            ("Günlük hacim / medyan", "d1_volr")]),
        ("RSI", [("Günlük RSI14", "d1_rsi"), ("4H RSI14", "h4_rsi"),
                 ("1H RSI14", "h1_rsi")]),
    ]
    for baslik, items in grp:
        rows = []
        for lab, col in items:
            if col not in d.columns:
                continue
            w = W[col].dropna(); l = L[col].dropna()
            r = cmp_row(lab, w, l)
            if r:
                rows.append(r)
        if rows:
            h.append(f"<h4>{baslik}</h4>")
            h.append(tbl(["Gösterge", "Kazananlar", "Kaybedenler", "Fark",
                          "Cohen's d", "Ayırt edicilik"], rows))

    # ── yön × sonuç ──
    h.append("<h3>5.4 Yön, saat ve gün kırılımı</h3>")
    rows = []
    for dr, g in d.groupby("dir"):
        rows.append([("LONG" if dr == "bull" else "SHORT"), len(g),
                     f"%{g.kazanan.mean()*100:.1f}", f"{g.r.sum():+.1f}",
                     f"{g.r.mean():+.3f}"])
    h.append(tbl(["Yön", "N", "WR", "Toplam R", "Ort R"], rows))
    return "\n".join(h)


def s_rejim(d, df_1h):
    """Volatilite ve trend rejimi analizi."""
    h = ['<h2 id="s6">6. Volatilite ve Trend Rejimi</h2>']
    dd = df_1h.Close.resample("D").last().dropna()
    hi = df_1h.High.resample("D").max().reindex(dd.index)
    lo = df_1h.Low.resample("D").min().reindex(dd.index)
    up, dn = hi.diff(), -lo.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([hi - lo, (hi - dd.shift()).abs(),
                    (lo - dd.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=dd.index).ewm(alpha=1/14, adjust=False).mean() / atr
    mdi = 100 * pd.Series(mdm, index=dd.index).ewm(alpha=1/14, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = dx.ewm(alpha=1/14, adjust=False).mean()
    d2 = d.copy(); d2["ym"] = d2["exit"].dt.to_period("M")
    m = d2.groupby("ym").agg(R=("r", "sum"), N=("r", "size"),
                             WR=("kazanan", lambda x: x.mean()*100))
    ctx = pd.DataFrame({
        "net": dd.pct_change().resample("ME").sum()*100,
        "eff": dd.pct_change().resample("ME").apply(
            lambda x: abs(x.sum())/x.abs().sum() if x.abs().sum() > 0 else 0),
        "adx": adx.resample("ME").mean()})
    ctx.index = ctx.index.to_period("M")
    m = m.join(ctx).dropna(subset=["R"])
    def rej(r):
        if r.eff >= .30 and r.net > 1:   return "YÜKSELİŞ"
        if r.eff >= .30 and r.net < -1:  return "DÜŞÜŞ"
        if r.eff < .18:                  return "AKÜMÜLASYON"
        return "ZAYIF/KARIŞIK"
    m["rejim"] = m.apply(rej, axis=1)
    rows = []
    for rj, g in m.groupby("rejim"):
        rows.append([rj, len(g), f"{g.R.sum():+.1f}", f"{g.R.mean():+.2f}",
                     f"%{(g.R>0).mean()*100:.0f}", f"%{g.WR.mean():.1f}",
                     f"{g.adx.mean():.1f}"])
    h.append(tbl(["Rejim", "Ay", "Toplam R", "Ay başı ort", "Pozitif ay",
                  "Ort WR", "Ort ADX"], rows,
                 "Rejim: Kaufman verimlilik oranı (|net|/Σ|değişim|) + aylık getiri. "
                 "Zarar eden ayların çoğu AKÜMÜLASYON — sistem düşüş trendinden "
                 "değil, trendin YOKLUĞUNDAN zarar ediyor."))
    rows = []
    for lo_, hi_ in [(0, 20), (20, 25), (25, 30), (30, 100)]:
        g = m[(m.adx >= lo_) & (m.adx < hi_)]
        if len(g):
            rows.append([f"{lo_}–{hi_ if hi_ < 100 else '+'}", len(g),
                         f"{g.R.sum():+.1f}", f"{g.R.mean():+.2f}",
                         f"%{(g.R>0).mean()*100:.0f}"])
    h.append("<h3>ADX kovaları (aylık ortalama)</h3>")
    h.append(tbl(["ADX", "Ay", "Toplam R", "Ort", "Pozitif ay"], rows,
                 "DİKKAT: bu aylık ilişki GERÇEK ama işlem seviyesine "
                 "ÇEVRİLEMEDİ — günlük ADX kapısı test edildiğinde kâr düştü "
                 "(+155R → +128R). Aylık istatistik ≠ işlem filtresi."))
    return "\n".join(h)


def s_perf(d):
    """Aylık / yıllık performans + grafikler."""
    h = ['<h2 id="s7">7. Performans: yıl yıl, ay ay</h2>']
    bal = 10000.0; cur = []
    for _, x in d.iterrows():
        delta = bal * 0.01 * x.r; bal += delta
        cur.append((x["exit"], bal, x.r, delta))
    c = pd.DataFrame(cur, columns=["t", "bal", "r", "usd"])
    c["y"] = c.t.dt.year; c["m"] = c.t.dt.month
    peak = c["bal"].cummax(); ddv = (peak - c["bal"]) / peak * 100

    fig, ax = plt.subplots(2, 1, figsize=(12, 6), sharex=True,
                           gridspec_kw={"height_ratios": [2.5, 1]},
                           facecolor="#12161c")
    dark(ax)
    ax[0].plot(c.t, c["bal"], lw=1.6, color="#26a69a")
    ax[0].set_ylabel("Kasa $", color="#9fb0c4")
    ax[0].set_title("Bileşik kasa eğrisi (10.000$ başlangıç, %1 risk)",
                    color="#e6edf5")
    ax[1].fill_between(c.t, -ddv, 0, color="#ef5350", alpha=.6)
    ax[1].set_ylabel("Drawdown %", color="#9fb0c4")
    h.append(img(fig, "equity"))

    rows = []; prev = 10000.0
    for y, g in c.groupby("y"):
        son = g["bal"].iloc[-1]
        rows.append([y, len(g), f"{g.r.sum():+.1f}", f"{son:,.0f}$",
                     f"%{(son/prev-1)*100:+.1f}"])
        prev = son
    h.append(tbl(["Yıl", "İşlem", "R", "Kasa sonu", "Yıl getirisi"], rows))

    AY = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu",
          "Eyl", "Eki", "Kas", "Ara"]
    piv = c.pivot_table(index="y", columns="m", values="usd",
                        aggfunc="sum").fillna(0).round(0)
    piv.columns = [AY[int(x)-1] for x in piv.columns]
    piv["YIL"] = piv.sum(axis=1)
    rows = []
    for y, r in piv.iterrows():
        cells = []
        for cname in piv.columns:
            v = r[cname]
            cls = "p" if v > 0 else ("n" if v < 0 else "")
            cells.append(f'<span class="{cls}">{v:,.0f}</span>' if v else "—")
        rows.append([y] + cells)
    h.append("<h3>Ay ay net PnL ($)</h3>")
    h.append(tbl(["Yıl"] + list(piv.columns), rows))
    mm = c.groupby(c.t.dt.to_period("M")).r.sum()
    h.append(f'<p class="note">{(mm>0).sum()}/{len(mm)} ay artıda '
             f'(%{(mm>0).mean()*100:.0f}). En iyi ay {mm.max():+.1f}R, '
             f'en kötü ay {mm.min():+.1f}R.</p>')

    fig, ax = plt.subplots(figsize=(12, 3.2), facecolor="#12161c")
    dark(ax)
    cols = np.where(mm.values > 0, "#26a69a", "#ef5350")
    ax.bar(range(len(mm)), mm.values, color=cols)
    ax.set_xticks(range(0, len(mm), 3))
    ax.set_xticklabels([str(x) for x in mm.index[::3]], rotation=45, fontsize=7)
    ax.set_ylabel("Aylık R", color="#9fb0c4")
    ax.set_title("Aylık R dağılımı", color="#e6edf5")
    h.append(img(fig, "aylik"))

    fig, ax = plt.subplots(1, 2, figsize=(12, 3.4), facecolor="#12161c")
    dark(ax)
    ax[0].hist(d.r, bins=40, color="#4C78A8")
    ax[0].axvline(0, color="#f5c542", lw=1)
    ax[0].set_title("İşlem R dağılımı", color="#e6edf5")
    for s_, g in d.groupby("s"):
        ax[1].plot(g["exit"], g.r.cumsum(), lw=1.4, label=s_)
    ax[1].legend(fontsize=8, facecolor="#1a222c", labelcolor="#9fb0c4")
    ax[1].set_title("Strateji bazında kümülatif R", color="#e6edf5")
    h.append(img(fig, "dagilim"))
    return "\n".join(h), bal, ddv.max(), (mm > 0).mean()*100


def s_canli():
    return """
<h2 id="s8">8. Canlıya Geçiş Notları</h2>
<div class="kutu red">
<b>Backtest sonucu gerçek para değildir.</b> Aşağıdakiler tavsiye değil,
bu sistemin bilinen sınırlarıdır.
</div>
<ul>
<li><b>WR %33 — ardışık kayıplar normaldir.</b> Ölçülen en uzun kayıp serisi
<b>13 işlem</b>. Sistem kârını nadir büyük kazançlardan alır; 8-10 ardışık
kaybı görmeden gerçek sermaye koymak psikolojik olarak risklidir.</li>
<li><b>Önce kağıt işlem.</b> <code>--dry-run</code> ile en az birkaç hafta
koşturup canlı fill fiyatlarını backtest varsayımlarıyla (spread 0.30$,
slippage 0.05$/oz, limit doluş oranı) karşılaştırın.</li>
<li><b>Ücret tarifesi kritik.</b> Sistem BingX VIP0'a (taker %0.05 / maker %0.02)
göre optimize edildi. Tarifeniz farklıysa <code>config/default.json → costs</code>
güncellenmeli ve testler tekrarlanmalı — ücret, RR ve stop genişliği seçimlerini
doğrudan belirliyor.</li>
<li><b>Veri kaynağı farkı.</b> Backtest Dukascopy verisiyle koştu; BingX'in
kendi mumları farklı olabilir (farklı broker = farklı wick/high-low). Mum-birebir
doğrulama için <code>colab_download_tradingview.py</code> kullanılabilir.</li>
<li><b>Parite korunmalı.</b> Live trader RR, min_stop_pct, SMA200 trend kapısı
ve swing stop'u config'ten okur. Config'te yapılan her değişiklik iki tarafı da
etkiler; tek taraflı elle düzenleme yapmayın.</li>
<li><b>2026 verisi kısmi.</b> Son yıl Temmuz'da bitiyor; o yılın rakamları
7 aylıktır.</li>
</ul>"""


def main():
    from gui import _load_data
    from config import get_config
    cfg = get_config()
    OUT.mkdir(parents=True, exist_ok=True)
    print("Veri yükleniyor...")
    df_1h, df_5m, _ = _load_data()
    print("Bağlam göstergeleri (5M/15M/1H/4H/1D)...")
    ctx = build_context(df_5m, df_1h)
    print("Backtest koşuluyor...")
    d = build_ledger(ctx)
    d.to_csv(OUT / "nihai_islem_defteri.csv", index=False, encoding="utf-8-sig")
    print(f"  defter: {len(d)} işlem")

    perf_html, bal, mdd, aypoz = s_perf(d)
    cfg_rows = []
    for s, sec in [("fvg", "fvg"), ("harmonic", "harmonic"),
                   ("threevol", "threevol")]:
        cfg_rows.append([s,
                         cfg.get(sec, "rr", default="—"),
                         cfg.get(sec, "poi_mode", default="—"),
                         f"%{cfg.get(sec, 'min_stop_pct', default=0)}",
                         "açık" if cfg.get(sec, "swing_stop", default=False) else "kapalı",
                         cfg.get(sec, "entry_order", default="—"),
                         "açık" if cfg.get(sec, "daily_trend_filter", default=False) else "kapalı"])
    sistem = ("<h3>Sistemin bugünkü hali (config/default.json)</h3>"
              + tbl(["Strateji", "RR", "poi_mode", "min_stop", "swing stop",
                     "giriş", "SMA200 kapısı"], cfg_rows,
                    f"Ücret: taker %{cfg.get('costs','commission_pct',default=0)} / "
                    f"maker %{cfg.get('costs','maker_pct',default=0)}, "
                    f"spread {cfg.get('costs','spread_usd',default=0)}$, "
                    f"slippage {cfg.get('costs','slippage_usd',default=0)}$/oz · "
                    f"risk: her işlemde %{cfg.get('risk','risk_fraction',default=0)*100:.0f} "
                    f"(bileşik) · elenen stratejiler: london, qwe"))

    baslik = ["Yönetici Özeti", "Düzeltilen Hatalar", "Kabul Edilen Mekanizmalar",
              "Reddedilen Mekanizmalar", "İşlem Adli Analizi",
              "Volatilite ve Trend Rejimi", "Performans", "Canlıya Geçiş"]
    toc = ('<div class="toc">' + "".join(
        f'<a href="#s{i+1}">{i+1}. {t}</a>' for i, t in enumerate(baslik)) + "</div>")

    html = (f'<meta charset="utf-8"><title>XAUUSD Nihai Sistem Raporu</title>'
            f"<style>{CSS}</style>"
            f"<h1>XAUUSD Algoritmik Sistem — Nihai Rapor</h1>"
            f'<p class="note">Veri {d.entry.min().date()} → {d["exit"].max().date()} '
            f"(5 yıl, 61 ay) · gerçek BingX ücretleri · %1 uniform risk · "
            f"IS/OOS ayrımı {SPLIT.date()}</p>"
            + toc
            + s_ozet(d, bal, mdd, aypoz) + sistem
            + s_hatalar() + s_kabul() + s_red()
            + s_adli(d) + s_rejim(d, df_1h) + perf_html + s_canli())
    p = OUT / "NIHAI_RAPOR.html"
    p.write_text(html, encoding="utf-8")
    print(f"\nRapor → {p}  ({p.stat().st_size/1e6:.1f} MB)")
    print("BITTI")


if __name__ == "__main__":
    main()
