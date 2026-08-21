import sys, pandas as pd, numpy as np
sys.path.insert(0,'/home/user/erebb'); sys.path.insert(0,'/home/user/erebb/scripts')
from equity import event_equity, risk_for_dd
from hybrid_rr_lab import kosu
S=pd.Timestamp('2025-01-11')
b=kosu([],2.0); b.to_csv('.labtmp/hb_baz.csv',index=False)
eb=event_equity(b,0.01); nb=event_equity(b,risk_for_dd(b,eb['dd']))['final']
bi,bo=b[b.entry<S].r.sum(),b[b.entry>=S].r.sum()
print('BAZ N=%d IS=%+.1f OOS=%+.1f TOP=%+.1f DD=%.1f%% esit-riskte=%s$\n'%(
    len(b),bi,bo,bi+bo,eb['dd'],format(nb,',.0f').replace(',','.')),flush=True)

def rapor(ad,d):
    i,o=d[d.entry<S].r.sum(),d[d.entry>=S].r.sum()
    e=event_equity(d,0.01); n=event_equity(d,risk_for_dd(d,eb['dd']))['final']
    print('  %-22s N=%3d IS=%+6.1f(%+5.1f) OOS=%+6.1f(%+5.1f) TOP=%+6.1f DD=%4.1f%% esit-riskte=%8s$ (%+.0f%%)%s'%(
        ad,len(d),i,i-bi,o,o-bo,i+o,e['dd'],format(n,',.0f').replace(',','.'),100*(n/nb-1),
        '  KABUL' if (i>bi and o>bo and n>nb) else ''),flush=True)
    return d

print('1) RR INCE TARAMA — 1:2 tepesi keskin mi? (NY on 13-18)')
NY=[13,14,15,16,17]
for rr in (1.75,2.0,2.25,2.5):
    d=kosu(NY,rr); rapor('RR 1:%.2f'%rr,d)
    if abs(rr-2.0)<1e-9: d.to_csv('.labtmp/hb_ny2.csv',index=False)
print()
print('2) PENCERE KAYDIRMA — konuma duyarli mi? (RR 1:2)')
for ad,w in (('11-16',[11,12,13,14,15]),('12-17',[12,13,14,15,16]),
             ('13-18',NY),('14-19',[14,15,16,17,18]),('15-20',[15,16,17,18,19])):
    rapor('pencere %s'%ad,kosu(w,2.0))
