"""
Evaluate Signal B (Google Trends week-over-week change) point-in-time.

For every week, the factor row says when it became knowable (factor_asof).
Entry is the close of the first trading day ON OR AFTER factor_asof - never a
price from before the value existed. The h-day forward return from that close
is market-adjusted with the same equal-weighted benchmark Signal A uses.

The test is a weekly cross-sectional rank IC (Fama-MacBeth style): one
Spearman correlation per week across tickers, then the mean and its standard
error across weeks. With a 5-day horizon and weekly entries the observations
do not overlap, so the plain standard error is appropriate.

Writes one row per run to results/trends_ic_history.csv, and reports how many
weeks rest on point-in-time vintages versus revision-prone history.
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import math

import compute_ic as ci
import config
import utils

HORIZON = 5
MIN_NAMES_PER_WEEK = 30
OUT = config.RESULTS_DIR / "trends_ic_history.csv"
FIELDS = ["run_time", "signal", "horizon_days", "ic_mean", "ic_se", "ic_tstat", "n_weeks",
          "n_obs", "weeks_vintage", "first_week", "last_week", "flag", "n_tickers", "coverage"]
FULL_COVERAGE = 0.90   # below this share of the universe the row is logged as partial


def _append(res: dict) -> None:
    """Append one row; upgrade an older file's header in place if columns were added."""
    rows = []
    if OUT.exists():
        with open(OUT, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    rows.append(res)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def _load_factor():
    path = config.SIGNALS_DIR / "trends_factor.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run() -> dict:
    rows = _load_factor()
    if not rows:
        utils.log_run("trends_ic", "failed", 0, "insufficient data (no trends factor)")
        return {}
    bench = ci._build_benchmark([HORIZON])[HORIZON]
    prices = {}
    by_week: dict[str, list[tuple[float, float]]] = {}
    vintage_weeks: set[str] = set()
    tickers_used: set[str] = set()
    for r in rows:
        tk = r["ticker"]
        if tk not in prices:
            prices[tk] = ci._load_prices(tk)
        series = prices[tk]
        if len(series) < HORIZON + 2:
            continue
        dates = [d for d, _ in series]
        asof = dt.date.fromisoformat(r["factor_asof"])
        i = bisect.bisect_left(dates, asof)          # first trading day >= asof
        if i + HORIZON >= len(series):
            continue
        d0, c0 = series[i]
        c1 = series[i + HORIZON][1]
        if not c0 or d0 not in bench:
            continue
        excess = (c1 / c0 - 1.0) - bench[d0][0]
        by_week.setdefault(r["week"], []).append((float(r["wow_change"]), excess))
        tickers_used.add(tk)
        if r.get("source") == "vintage":
            vintage_weeks.add(r["week"])

    ics, n_obs, used = [], 0, []
    for wk in sorted(by_week):
        pairs = by_week[wk]
        if len(pairs) < MIN_NAMES_PER_WEEK:
            continue
        ic = ci._spearman([p[0] for p in pairs], [p[1] for p in pairs])
        if ic is not None:
            ics.append(ic)
            n_obs += len(pairs)
            used.append(wk)

    k = len(ics)
    if k < 3:
        utils.log_run("trends_ic", "partial", k, f"insufficient data ({k} usable weeks)")
        return {"n_weeks": k}
    mean = sum(ics) / k
    se = math.sqrt(sum((v - mean) ** 2 for v in ics) / (k - 1) / k)
    t = mean / se if se else None
    flag = "LOOKAHEAD?" if abs(mean) > config.IC_LOOKAHEAD_THRESHOLD else (
        "SIGNIFICANT" if t is not None and abs(t) > 2 else "NOISE")
    universe = max(len(list(config.PRICES_DIR.glob("*.csv"))), 1)
    coverage = len(tickers_used) / universe
    res = {"run_time": utils.utcnow_iso(), "signal": "trends_wow", "horizon_days": HORIZON,
           "ic_mean": round(mean, 6), "ic_se": round(se, 6), "ic_tstat": round(t, 3) if t else None,
           "n_weeks": k, "n_obs": n_obs, "weeks_vintage": len(vintage_weeks & set(used)),
           "first_week": used[0], "last_week": used[-1], "flag": flag,
           "n_tickers": len(tickers_used), "coverage": round(coverage, 3)}
    _append(res)
    status = "success" if coverage >= FULL_COVERAGE else "partial"
    utils.log_run("trends_ic", status, k,
                  f"weekly IC {mean:+.4f} (t {t:+.2f}) over {k} weeks, {len(tickers_used)} tickers "
                  f"({coverage:.0%} of universe); {res['weeks_vintage']} weeks on point-in-time vintages")
    return res
