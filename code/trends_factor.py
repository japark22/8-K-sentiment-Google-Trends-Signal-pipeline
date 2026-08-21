"""
Signal B: Google Trends search-interest factor.

Feature = week-over-week change in search interest, using ONLY weeks that
have already closed. For a signal available at the start of week W, we use
the change between week W-2 and week W-1 (both fully public before W begins).
This prevents using the still-open current week (lookahead).

Output: signals/trends_factor.csv with columns:
  ticker, week, interest, wow_change, factor_asof
where factor_asof is the first date on which the factor is knowable.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import config
import utils


def _load_weekly(path: Path) -> list[tuple[dt.date, int]]:
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                out.append((dt.date.fromisoformat(r["week"]), int(r["interest"])))
            except Exception:
                continue
    out.sort(key=lambda x: x[0])
    return out


def run() -> int:
    """Compute the WoW trends factor for every ticker. Returns rows written."""
    out_rows = []
    for path in sorted(config.TRENDS_DIR.glob("*.csv")):
        ticker = path.stem
        series = _load_weekly(path)
        # Need at least 2 prior weeks to form a change without lookahead.
        for i in range(1, len(series)):
            wk_prev, v_prev = series[i - 1]
            wk_cur, v_cur = series[i]
            wow = (v_cur - v_prev) / v_prev if v_prev else 0.0
            # The change between wk_prev and wk_cur is only fully knowable once
            # wk_cur has closed, i.e. from the following week onward.
            factor_asof = wk_cur + dt.timedelta(days=7)
            out_rows.append({
                "ticker": ticker,
                "week": wk_cur.isoformat(),
                "interest": v_cur,
                "wow_change": round(wow, 6),
                "factor_asof": factor_asof.isoformat(),
            })

    config.SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.SIGNALS_DIR / "trends_factor.csv"
    fields = ["ticker", "week", "interest", "wow_change", "factor_asof"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    utils.log_run("trends_factor", "success", len(out_rows),
                  f"{len(out_rows)} weekly factor rows")
    return len(out_rows)
