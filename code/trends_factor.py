"""
Signal B: Google Trends search-interest factor.

Feature = week-over-week change in search interest, using ONLY weeks that
have already closed. For a signal available at the start of week W, we use
the change between week W-2 and week W-1 (both fully public before W begins).
This prevents using the still-open current week (lookahead).

Output: signals/trends_factor.csv with columns:
  ticker, week, interest, wow_change, factor_asof, source
where factor_asof is the first date on which the factor is knowable.

Google rescales a series on every request, so values in data/trends/ are the
LATEST revision ("revised"). Where fetch_trends.py has logged a vintage - the
two newest closed weeks as they looked on a given retrieval date - the factor
for that week is taken from the earliest vintage instead ("vintage"): exactly
the number a model could have computed then. History before the vintage log
existed stays "revised" and is documented as revision-prone.
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
                "source": "revised",
            })

    # Point-in-time vintages override revised values for the same ticker-week.
    vint_dir = config.DATA_DIR / "trends_vintages"
    by_key = {(r["ticker"], r["week"]): r for r in out_rows}
    n_vint = 0
    for path in sorted(vint_dir.glob("*.csv")) if vint_dir.exists() else []:
        ticker = path.stem
        pulls: dict[str, list[tuple[str, int]]] = {}
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    pulls.setdefault(r["retrieved"], []).append((r["week"], int(r["interest"])))
                except Exception:
                    continue
        for retrieved in sorted(pulls):                      # earliest vintage wins
            pts = sorted(pulls[retrieved])
            if len(pts) < 2:
                continue
            (w_prev, v_prev), (w_cur, v_cur) = pts[-2], pts[-1]
            key = (ticker, w_cur)
            if key in by_key and by_key[key]["source"] == "vintage":
                continue
            by_key[key] = {
                "ticker": ticker, "week": w_cur, "interest": v_cur,
                "wow_change": round((v_cur - v_prev) / v_prev if v_prev else 0.0, 6),
                "factor_asof": max(retrieved,
                                   (dt.date.fromisoformat(w_cur) + dt.timedelta(days=7)).isoformat()),
                "source": "vintage",
            }
            n_vint += 1
    out_rows = sorted(by_key.values(), key=lambda r: (r["ticker"], r["week"]))

    config.SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.SIGNALS_DIR / "trends_factor.csv"
    fields = ["ticker", "week", "interest", "wow_change", "factor_asof", "source"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    utils.log_run("trends_factor", "success", len(out_rows),
                  f"{len(out_rows)} weekly factor rows ({n_vint} from point-in-time vintages)")
    return len(out_rows)
