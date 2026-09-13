"""KR daily prices via pykrx (KRX public data) — APAC Phase 1.
Reads unique stock codes from data/kr_filings/dart_list.csv and saves daily
OHLCV per ticker to data/kr_prices/<code>.csv. Used for point-in-time
forward returns after each disclosure."""
from __future__ import annotations
import sys, csv, time, datetime as dt
from pathlib import Path
from pykrx import stock

BASE = Path(__file__).resolve().parent.parent
LIST = BASE / "data" / "kr_filings" / "dart_list.csv"
OUTDIR = BASE / "data" / "kr_prices"
LOOKBACK_DAYS = 760

def codes():
    out, seen = [], set()
    with open(LIST, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c = (r.get("stock_code") or "").strip()
            if len(c) == 6 and c.isdigit() and c not in seen:
                seen.add(c); out.append(c)
    return out

def run(limit=None):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    end = dt.date.today(); bgn = end - dt.timedelta(days=LOOKBACK_DAYS)
    b, e = bgn.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    cs = codes()
    if limit: cs = cs[:limit]
    ok = fail = 0
    for i, c in enumerate(cs, 1):
        try:
            df = stock.get_market_ohlcv(b, e, c)
            if df is None or df.empty:
                fail += 1; continue
            with open(OUTDIR / f"{c}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["date","open","high","low","close","volume"])
                for idx, row in df.iterrows():
                    w.writerow([idx.strftime("%Y-%m-%d"), int(row["시가"]),
                                int(row["고가"]), int(row["저가"]),
                                int(row["종가"]), int(row["거래량"])])
            ok += 1
        except Exception as exc:
            fail += 1; print(f"  {c} failed: {exc}")
        time.sleep(0.2)
        if i % 25 == 0: print(f"  {i}/{len(cs)} done...")
    print(f"KR prices: {ok} saved, {fail} failed -> {OUTDIR}")

if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else None)
