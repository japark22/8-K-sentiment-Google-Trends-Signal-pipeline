"""Rigor checks on the KR disclosure-sentiment signal (APAC Phase 1).
Per horizon: raw IC, market-adjusted IC (returns demeaned cross-sectionally
per receipt date), long-short spread (positive- vs negative-tone events),
and sub-period stability (first vs second half)."""
from __future__ import annotations
import csv
from pathlib import Path
from collections import defaultdict
BASE=Path(__file__).resolve().parent.parent
SRC=BASE/"signals"/"kr_aligned.csv"
HZ=["r1","r2","r3","r5"]
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
def load():
    rows=[]
    with open(SRC,encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d={"date":r["rcept_dt"],"tone":float(r["tone"])}
            for h in HZ:
                v=r.get(h,""); d[h]=float(v) if v not in ("",None) else None
            rows.append(d)
    return rows
def adj(rows,h):
    by=defaultdict(list)
    for r in rows:
        if r[h] is not None: by[r["date"]].append(r[h])
    m={d:sum(v)/len(v) for d,v in by.items()}
    return [(r["tone"], r[h]-m[r["date"]], r["date"]) for r in rows if r[h] is not None]
def f(x): return "n/a" if x is None else round(x,4)
def run():
    rows=load(); print(f"Total aligned events: {len(rows)}\n")
    for h in HZ:
        raw=[(r["tone"],r[h]) for r in rows if r[h] is not None]
        ic_raw=spearman([a for a,_ in raw],[b for _,b in raw])
        a=adj(rows,h); ic_adj=spearman([x for x,_,_ in a],[y for _,y,_ in a])
        pos=[y for x,y,_ in a if x>0]; neg=[y for x,y,_ in a if x<0]
        ls=(sum(pos)/len(pos)-sum(neg)/len(neg)) if pos and neg else None
        ds=sorted(set(d for _,_,d in a)); mid=ds[len(ds)//2] if ds else None
        a1=[(x,y) for x,y,d in a if d<mid]; a2=[(x,y) for x,y,d in a if d>=mid]
        ic1=spearman([x for x,_ in a1],[y for _,y in a1]); ic2=spearman([x for x,_ in a2],[y for _,y in a2])
        lsp=f(ls*100) if ls is not None else "n/a"
        print(f"{h}: rawIC={f(ic_raw)}  mktAdjIC={f(ic_adj)}  LS(pos-neg)={lsp}%  stability[1st/2nd]={f(ic1)}/{f(ic2)}  n={len(raw)}")
if __name__=="__main__":
    run()
