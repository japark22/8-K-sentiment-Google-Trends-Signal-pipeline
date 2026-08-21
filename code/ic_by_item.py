"""
Break the 8-K sentiment IC down by 8-K item number.

WHY
---
An 8-K is a container, not an event type. Item 2.02 is results of operations,
5.02 an officer resignation, 1.01 a material agreement, 5.07 the outcome of a
shareholder vote. Scoring the tone of all of them together and correlating
with forward returns asks whether "8-K language" predicts returns, which is
close to meaningless: a positive earnings release and a warmly-worded
executive departure pull in opposite directions and cancel.

This splits the existing aligned panel by item and reports each separately.
No new data is fetched -- it joins signals/aligned_returns.csv to the `items`
column now stored in data/filings_8k/*.csv.

Item 9.01 is "Financial Statements and Exhibits", a filing-mechanics item that
accompanies many others and carries no event meaning, so it is stripped before
picking the group. A filing's group is its first remaining item.

MULTIPLE TESTING
----------------
Splitting one sample into k groups and reporting the best one is how noise
gets published. Two guards:

  1. HYPOTHESES ARE FIXED BEFORE LOOKING. Stated in EXPECTATION below:
     2.02 is expected to carry signal; 7.01 and 8.01 are expected to be null.
     A result in a group marked "exploratory" is a hypothesis for a later
     sample, not a finding in this one.

  2. A BONFERRONI THRESHOLD IS PRINTED alongside the conventional 1.96, and
     every group is shown -- including the ones that found nothing. There is
     no way to read this table and see only the winner.

CONTROL GROUP
-------------
Item 5.07 reports the tally of a shareholder vote. It is procedural: the
outcome is known before the filing and it says nothing about the business. It
is included as a PLACEBO. If tone on 5.07 filings predicts returns, the
finding is a bug in the alignment or the return construction, not an edge.

Output: results/ic_by_item.csv, plus a table on stdout.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import sys
from pathlib import Path
from statistics import NormalDist

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import compute_ic

# Groups reported, and what we said about them BEFORE running.
EXPECTATION = {
    "2.02": "signal expected (results of operations)",
    "7.01": "null expected (Reg FD disclosure)",
    "8.01": "null expected (other events)",
    "5.02": "exploratory (officer/director change)",
    "1.01": "exploratory (material agreement)",
    "5.07": "PLACEBO (shareholder vote tally)",
}
MIN_FILINGS = 200      # below this a group is listed but not tested
MIN_DATES = 10         # below this the by-date estimate is not reported


def load_items() -> dict:
    """accession -> group item, from the filings metadata."""
    out = {}
    for path in sorted(glob.glob(str(config.FILINGS_DIR / "*.csv"))):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                raw = (r.get("items") or "").strip()
                parts = [x.strip() for x in raw.split(",")
                         if x.strip() and x.strip() != "9.01"]
                out[r["accession"]] = parts[0] if parts else "(none)"
    return out


def load_aligned(horizons):
    path = config.SIGNALS_DIR / "aligned_returns.csv"
    if not path.exists():
        sys.exit("no signals/aligned_returns.csv -- run the ic stage first")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rec = {"accession": r["accession"],
                   "date": dt.date.fromisoformat(r["entry_date"]),
                   "tone": float(r["tone"])}
            for h in horizons:
                for key in (f"fwd_ret_{h}d", f"exc_ret_{h}d"):
                    v = r.get(key, "")
                    rec[key] = float(v) if v not in ("", None) else None
            rows.append(rec)
    return rows


def fmt(v, nd=4):
    return "   n/a  " if v is None else f"{v:+.{nd}f}"


def main() -> None:
    horizons = list(config.FORWARD_HORIZONS)
    items = load_items()
    aligned = load_aligned(horizons)

    unmatched = sum(1 for r in aligned if r["accession"] not in items)
    for r in aligned:
        r["group"] = items.get(r["accession"], "(unmatched)")

    counts = {}
    for r in aligned:
        counts[r["group"]] = counts.get(r["group"], 0) + 1

    groups = [g for g in EXPECTATION if counts.get(g, 0) >= MIN_FILINGS]
    n_tests = len(groups) * len(horizons)
    bonf = NormalDist().inv_cdf(1 - 0.05 / (2 * n_tests)) if n_tests else float("nan")

    print(f"\naligned filings {len(aligned):,}   "
          f"unmatched to an item {unmatched:,}")
    print(f"tests run {n_tests}  ->  Bonferroni |t| threshold {bonf:.2f} "
          f"(conventional 1.96)")
    print("=" * 92)
    print(f"{'item':<6}{'n':>6}{'h':>4}{'pooled exc':>13}{'t':>7}"
          f"{'by-date':>12}{'t':>7}{'dates':>7}   verdict")
    print("-" * 92)

    out_rows = []
    for g in EXPECTATION:
        n_g = counts.get(g, 0)
        if n_g < MIN_FILINGS:
            print(f"{g:<6}{n_g:>6}   -- below the {MIN_FILINGS}-filing floor, "
                  f"not tested ({EXPECTATION[g]})")
            continue

        sub = [r for r in aligned if r["group"] == g]
        for h in horizons:
            exc = [(r["date"], r["tone"], r[f"exc_ret_{h}d"]) for r in sub
                   if r[f"exc_ret_{h}d"] is not None]
            pooled = compute_ic._pooled([x[1] for x in exc], [x[2] for x in exc])
            byd = compute_ic._per_date(exc)

            bt = byd["t"] if byd["n_dates"] >= MIN_DATES else None
            bic = byd["ic"] if byd["n_dates"] >= MIN_DATES else None

            if bt is None:
                verdict = "too few dates"
            elif abs(bt) >= bonf:
                verdict = "SURVIVES Bonferroni"
            elif abs(bt) >= 1.96:
                verdict = "nominal only"
            else:
                verdict = "noise"

            print(f"{g:<6}{n_g:>6}{h:>3}d{fmt(pooled['ic']):>13}"
                  f"{fmt(pooled['t'], 2):>7}{fmt(bic):>12}{fmt(bt, 2):>7}"
                  f"{byd['n_dates']:>7}   {verdict}")

            out_rows.append({
                "item": g, "expectation": EXPECTATION[g], "n_filings": n_g,
                "horizon_days": h,
                "ic_excess_pooled": compute_ic._r(pooled["ic"]),
                "t_pooled": compute_ic._r(pooled["t"], 3),
                "ic_excess_bydate": compute_ic._r(bic),
                "t_bydate": compute_ic._r(bt, 3),
                "n_dates": byd["n_dates"],
                "bonferroni_t": round(bonf, 3),
                "verdict": verdict,
            })
        print("-" * 92)

    print("\nexpectations fixed before running:")
    for g, why in EXPECTATION.items():
        print(f"  {g:<6} {why}")
    print("\nRead the by-date t, not the pooled one. A group marked "
          "'exploratory' or 'nominal only'")
    print("is a hypothesis for the next sample, not a result in this one. "
          "5.07 is the placebo:")
    print("if it shows anything, suspect the alignment before believing "
          "any other row.\n")

    if out_rows:
        config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        dest = config.RESULTS_DIR / "ic_by_item.csv"
        with open(dest, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            w.writerows(out_rows)
        print(f"wrote {dest.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
