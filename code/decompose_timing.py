"""
Where does the 8-K tone signal live in time? No new data is fetched.

THE PROBLEM WITH THE CURRENT ENTRY RULE
---------------------------------------
compute_ic anchors entry to the CLOSE of the first bar strictly after the
acceptance date. That was chosen as a lookahead guard, and as a guard it is
correct: an 8-K accepted at 20:23 ET has its own day's close already set, so
that close is unusable.

But the guard is stricter than it needs to be. If the news is public at 20:23
on day D, the OPEN of day D+1 is a price you could actually trade -- it comes
after the information, not before. By entering at D+1's close instead, we skip
the entire first session. If a tone effect exists and is consumed on the day
after the filing, the current measurement cannot see it by construction, and
would report zero however good the signal is.

WHAT THIS MEASURES
------------------
For each filing, with ei = index of the first bar strictly after acceptance:

  gap      open[ei]  / close[ei-1] - 1   the overnight move. NOT tradable at
                                         our entry: it happens before the
                                         first price we could transact at.
  session  close[ei] / open[ei]    - 1   the first full session after the
                                         news. Tradable from the open.
  open->h  close[ei+h] / open[ei]  - 1   enter at the open, hold h days.
                                         Tradable, and includes `session`.
  close->h close[ei+h] / close[ei] - 1   what compute_ic reports today.

Every one is market-adjusted against an equal-weighted benchmark built the
same way over the whole price universe, so a common market move on the filing
date cannot masquerade as signal.

HOW TO READ IT
--------------
If tone shows up in `gap` and nowhere else, the information is real but priced
before anyone could act on it -- interesting, not tradable, and it explains a
zero IC without any bug.

If tone shows up in `session` or `open->h` but not `close->h`, the signal is
real AND tradable, and the current entry rule was throwing it away.

If nothing shows up anywhere, the tone measure itself carries no short-horizon
information, and no amount of extra history fixes that.

Judge on the by-date t, for the same reason as compute_ic: filings cluster on
dates and the pooled t treats clustered observations as independent.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import compute_ic

MIN_BENCH = 30          # tickers needed before a date's benchmark is usable
GROUPS = ("ALL", "2.02", "5.07")   # 5.07 stays in as the placebo


def load_ohlc(ticker):
    """[(date, open, close)] ascending, rows with a usable close only."""
    path = config.PRICES_DIR / f"{ticker}.csv"
    if not path.exists():
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                c = float(r["close"])
                o = float(r["open"]) if r.get("open") not in ("", None) else None
            except (ValueError, TypeError, KeyError):
                continue
            out.append((dt.date.fromisoformat(r["date"]), o, c))
    out.sort(key=lambda x: x[0])
    return out


def measures(series, i, horizons):
    """The four return definitions at bar i, or None where undefined."""
    d, o, c = series[i]
    out = {}
    prev_c = series[i - 1][2] if i >= 1 else None
    out["gap"] = (o / prev_c - 1.0) if (o and prev_c) else None
    out["session"] = (c / o - 1.0) if o else None
    for h in horizons:
        j = i + h
        cj = series[j][2] if j < len(series) else None
        out[f"open{h}"] = (cj / o - 1.0) if (cj and o) else None
        out[f"close{h}"] = (cj / c - 1.0) if (cj and c) else None
    return out


def main() -> None:
    horizons = list(config.FORWARD_HORIZONS)
    keys = ["gap", "session"] + [f"open{h}" for h in horizons] \
                              + [f"close{h}" for h in horizons]

    # ---- prices + benchmark ------------------------------------------------
    tickers = sorted(p.stem for p in Path(config.PRICES_DIR).glob("*.csv"))
    prices, sums = {}, {}
    for tk in tickers:
        s = load_ohlc(tk)
        if len(s) < 2:
            continue
        prices[tk] = {"series": s, "idx": {d: i for i, (d, _, _) in enumerate(s)}}
        for i in range(len(s)):
            m = measures(s, i, horizons)
            day = sums.setdefault(s[i][0], {k: [0.0, 0] for k in keys})
            for k in keys:
                if m[k] is not None:
                    day[k][0] += m[k]
                    day[k][1] += 1
    bench = {d: {k: (t / n) for k, (t, n) in v.items() if n >= MIN_BENCH}
             for d, v in sums.items()}
    print(f"prices loaded for {len(prices):,} tickers, "
          f"benchmark on {len(bench):,} dates")

    # ---- items -------------------------------------------------------------
    items = {}
    for path in sorted(glob.glob(str(config.FILINGS_DIR / "*.csv"))):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                raw = (r.get("items") or "").strip()
                parts = [x.strip() for x in raw.split(",")
                         if x.strip() and x.strip() != "9.01"]
                items[r["accession"]] = parts[0] if parts else "(none)"

    # ---- filings -> per-measure excess returns -----------------------------
    sent = config.SIGNALS_DIR / "sentiment.csv"
    if not sent.exists():
        sys.exit("no signals/sentiment.csv")

    recs = []
    skipped = 0
    with open(sent, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            tk = r["ticker"]
            if tk not in prices:
                skipped += 1
                continue
            acc_dt = compute_ic._parse_accepted(r.get("accepted_datetime", ""))
            if acc_dt is None:
                skipped += 1
                continue
            s = prices[tk]["series"]
            ei = None
            for i, (d, _, _) in enumerate(s):
                if d > acc_dt.date():
                    ei = i
                    break
            if ei is None or ei == 0:      # need bar ei-1 for the gap
                skipped += 1
                continue
            m = measures(s, ei, horizons)
            b = bench.get(s[ei][0], {})
            rec = {"date": s[ei][0], "tone": float(r["tone"]),
                   "group": items.get(r["accession"], "(none)")}
            for k in keys:
                rec[k] = (m[k] - b[k]) if (m[k] is not None and k in b) else None
            recs.append(rec)

    print(f"filings aligned {len(recs):,}   skipped {skipped:,}\n")

    # ---- report ------------------------------------------------------------
    label = {"gap": "gap: overnight [not tradable]",
             "session": "session: open->close, day 1"}
    for h in horizons:
        label[f"open{h}"] = f"open -> +{h}d close [tradable]"
        label[f"close{h}"] = f"close -> +{h}d close [CURRENT]"

    for g in GROUPS:
        sub = recs if g == "ALL" else [r for r in recs if r["group"] == g]
        tag = "all 8-K" if g == "ALL" else f"item {g}"
        if g == "5.07":
            tag += "  [PLACEBO]"
        print("=" * 78)
        print(f"{tag}   n = {len(sub):,}")
        print(f"  {'measure':<32}{'IC':>10}{'t':>8}{'dates':>7}")
        print("  " + "-" * 57)
        for k in keys:
            rows = [(r["date"], r["tone"], r[k]) for r in sub if r[k] is not None]
            d = compute_ic._per_date(rows)
            ic = "    n/a" if d["ic"] is None else f"{d['ic']:+.4f}"
            t = "   n/a" if d["t"] is None else f"{d['t']:+.2f}"
            print(f"  {label[k]:<32}{ic:>10}{t:>8}{d['n_dates']:>7}")
        print()

    print("A signal in `gap` only means it is real but priced before our entry.")
    print("A signal in `session`/`open->h` but not `close->h` means the current")
    print("entry rule was discarding it. Nothing anywhere means the tone")
    print("measure carries no short-horizon information.")


if __name__ == "__main__":
    main()
