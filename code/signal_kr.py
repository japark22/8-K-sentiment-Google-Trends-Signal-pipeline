"""KR disclosure-sentiment signal v1 (APAC Phase 1).
Sentiment = keyword lexicon over the disclosure title (report_nm).
Point-in-time: forward returns from the first trading day AFTER rcept_dt.
Evaluation: Spearman rank IC (tone vs forward return) per horizon."""
from __future__ import annotations
import csv, datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LIST = BASE/"data"/"kr_filings"/"dart_list.csv"
PRICES = BASE/"data"/"kr_prices"
OUT = BASE/"signals"/"kr_aligned.csv"
HORIZONS = [1,2,3,5]
POS = ["공급계약","수주","단일판매","계약체결","자기주식취득","자사주","흑자","흑자전환",
       "무상증자","배당","특허","승인","허가","최대","신규시설투자","취득"]
NEG = ["유상증자","감자","적자","적자전환","손실","소송","제소","횡령","배임","부도",
       "파산","회생","상장폐지","관리종목","거래정지","자본잠식","불성실공시","해지","철회"]

def tone(title):
    t=title or ""; p=sum(t.count(w) for w in POS); n=sum(t.count(w) for w in NEG)
    return ((p-n)/(p+n) if (p+n) else 0.0)

def load_prices(code):
    f=PRICES/f"{code}.csv"
    if not f.exists(): return [],[]
    ds,cs=[],[]
    with open(f,encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try: ds.append(dt.date.fromisoformat(r["date"])); cs.append(float(r["close"]))
            except: pass
    return ds,cs

def spearman(x,y):
    n=len(x)
    if n<3: return None
    def rank(v):
        o=sorted(range(len(v)),key=lambda i:v[i]); rk=[0.0]*len(v); i=0
        while i<len(v):
            j=i
            while j+1<len(v) and v[o[j+1]]==v[o[i]]: j+=1
            a=(i+j)/2+1
            for k in range(i,j+1): rk[o[k]]=a
            i=j+1
        return rk
    rx,ry=rank(x),rank(y); mx=sum(rx)/n; my=sum(ry)/n
    cov=sum((a-mx)*(b-my) for a,b in zip(rx,ry))
    vx=sum((a-mx)**2 for a in rx)**.5; vy=sum((b-my)**2 for b in ry)**.5
    return cov/(vx*vy) if vx and vy else None

def run():
    aligned=[]
    with open(LIST,encoding="utf-8") as f:
        for r in csv.DictReader(f):
            code=(r.get("stock_code") or "").strip()
            if len(code)!=6: continue
            try: rc=dt.datetime.strptime(r["rcept_dt"].strip(),"%Y%m%d").date()
            except: continue
            tv=tone(r.get("report_nm",""))
            if tv==0: continue
            ds,cs=load_prices(code)
            if not ds: continue
            ei=next((i for i,d in enumerate(ds) if d>rc),None)
            if ei is None: continue
            row={"code":code,"rcept_dt":rc.isoformat(),"tone":tv,
                 "report_nm":(r.get("report_nm","") or "").strip()}
            has=False
            for h in HORIZONS:
                j=ei+h
                row[f"r{h}"]=(cs[j]/cs[ei]-1) if (j<len(cs) and cs[ei]) else ""
                if isinstance(row[f"r{h}"],float): has=True
            if has: aligned.append(row)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    fields=["code","rcept_dt","tone","report_nm"]+[f"r{h}" for h in HORIZONS]
    with open(OUT,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for row in aligned:
            w.writerow({k:(round(v,6) if isinstance(v,float) else v) for k,v in row.items()})
    print(f"Aligned {len(aligned)} scored KR disclosures -> {OUT}")
    for h in HORIZONS:
        xs=[a["tone"] for a in aligned if isinstance(a.get(f'r{h}'),float)]
        ys=[a[f'r{h}'] for a in aligned if isinstance(a.get(f'r{h}'),float)]
        ic=spearman(xs,ys)
        print(f"  IC {h}d: {'n/a' if ic is None else round(ic,4)} (n={len(xs)})")

if __name__=="__main__":
    run()
