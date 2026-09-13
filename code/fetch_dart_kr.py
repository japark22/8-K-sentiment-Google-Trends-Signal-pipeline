"""Korea (DART) disclosure-list fetcher — APAC Phase 1 (multi-year, chunked).
OpenDART limits each market-wide query to 3 months, so we loop 89-day chunks
over TOTAL_DAYS. Public free API. Requires env OPENDART_API_KEY."""
from __future__ import annotations
import os, csv, time, datetime as dt
from pathlib import Path
import requests
API="https://opendart.fss.or.kr/api/list.json"
OUT=Path(__file__).resolve().parent.parent/"data"/"kr_filings"/"dart_list.csv"
TOTAL_DAYS=730
CHUNK_DAYS=89
MARKETS=["Y","K"]
def fetch_range(key,mkt,bgn,end,seen,rows):
    page=1
    while True:
        params={"crtfc_key":key,"bgn_de":bgn.strftime("%Y%m%d"),
                "end_de":end.strftime("%Y%m%d"),"corp_cls":mkt,
                "page_no":page,"page_count":100}
        r=requests.get(API,params=params,timeout=30); r.raise_for_status()
        j=r.json(); st=j.get("status")
        if st=="013": break
        if st!="000":
            print(f"[{mkt} {bgn}~{end}] status {st}: {j.get('message')}"); break
        for it in j.get("list",[]):
            rn=it.get("rcept_no","")
            if rn in seen: continue
            seen.add(rn)
            rows.append({"stock_code":it.get("stock_code",""),
                         "corp_name":it.get("corp_name",""),
                         "market":it.get("corp_cls",""),
                         "report_nm":it.get("report_nm",""),
                         "rcept_no":rn,"rcept_dt":it.get("rcept_dt","")})
        if page>=j.get("total_page",1): break
        page+=1; time.sleep(0.2)
def run():
    key=os.environ.get("OPENDART_API_KEY")
    if not key: raise SystemExit("Set OPENDART_API_KEY env var first.")
    end=dt.date.today(); start=end-dt.timedelta(days=TOTAL_DAYS)
    rows=[]; seen=set(); cur=start
    while cur<end:
        ce=min(cur+dt.timedelta(days=CHUNK_DAYS), end)
        for mkt in MARKETS: fetch_range(key,mkt,cur,ce,seen,rows)
        print(f"  through {ce} ... {len(rows)} filings")
        cur=ce+dt.timedelta(days=1)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with open(OUT,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["stock_code","corp_name","market","report_nm","rcept_no","rcept_dt"])
        w.writeheader(); w.writerows(rows)
    print(f"Saved {len(rows)} KR filings ({start} to {end}) -> {OUT}")
if __name__=="__main__":
    run()
