"""
Fetch Google Trends weekly search interest via pytrends (public, unofficial).

Requests are throttled and batched (<=5 terms per request, which is the
Google Trends limit). Results are saved per ticker at
data/trends/<TICKER>.csv with columns: week, interest.

POINT-IN-TIME NOTE: Google Trends returns weekly values. When these are used
as a feature (trends_factor.py), only the value for a week that has already
CLOSED may inform a signal for the following period -- never the current,
still-open week. Trends also rescales historically; we store the values as
returned and treat them as a coarse, revision-prone feature (documented).
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

import config
import utils

# Google Trends throttles aggressively (HTTP 429). To stay a good citizen and
# fill coverage gradually, each run only fetches a limited number of NEW
# tickers, skips ones already saved (resume across days), paces requests, and
# stops early after several consecutive rate-limits.
MAX_NEW_PER_RUN = 40          # cap new tickers fetched per run
BASE_DELAY_SEC = 6.0          # spacing between successful requests
MAX_CONSECUTIVE_429 = 4       # stop the run after this many 429s in a row


def _is_rate_limited(exc: Exception) -> bool:
    return "429" in str(exc)


def run(tickers: list[str], name_map: dict[str, str] | None = None) -> int:
    """Fetch weekly interest for each ticker's company name.
    Resumes across runs (skips tickers already saved), fetches at most
    MAX_NEW_PER_RUN new tickers, and backs off / stops early on rate limits.
    Returns number of tickers newly fetched this run."""
    try:
        from pytrends.request import TrendReq
    except Exception as exc:  # noqa: BLE001
        utils.log_run("fetch_trends", "failed", 0,
                      f"pytrends not installed: {exc}")
        return 0

    name_map = name_map or {}
    try:
        pytrends = TrendReq(hl="en-US", tz=0)
    except Exception as exc:  # noqa: BLE001
        utils.log_run("fetch_trends", "failed", 0, f"TrendReq init failed: {exc}")
        return 0

    # Resume: only attempt tickers we don't already have a file for.
    pending = [tk for tk in tickers
               if not (config.TRENDS_DIR / f"{tk}.csv").exists()]
    already = len(tickers) - len(pending)
    batch = pending[:MAX_NEW_PER_RUN]

    n_ok, failures, consecutive_429 = 0, 0, 0
    stopped_early = False
    for tk in batch:
        term = name_map.get(tk, tk)
        try:
            pytrends.build_payload([term], timeframe=config.TRENDS_LOOKBACK)
            df = pytrends.interest_over_time()
            if df is None or df.empty or term not in df.columns:
                utils.log_run("fetch_trends_ticker", "partial", 0,
                              f"{tk}: insufficient data")
                consecutive_429 = 0
                continue
            out = config.TRENDS_DIR / f"{tk}.csv"
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["week", "interest"])
                for idx, val in df[term].items():
                    w.writerow([idx.strftime("%Y-%m-%d"), int(val)])
            n_ok += 1
            consecutive_429 = 0
            time.sleep(BASE_DELAY_SEC)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            utils.log_run("fetch_trends_ticker", "failed", 0, f"{tk}: {exc}")
            if _is_rate_limited(exc):
                consecutive_429 += 1
                if consecutive_429 >= MAX_CONSECUTIVE_429:
                    stopped_early = True
                    utils.log_run("fetch_trends", "partial", n_ok,
                                  "stopped early: Google Trends rate-limited "
                                  "(429). Will resume next run.")
                    break
                # Exponential backoff on rate limits: 15s, 30s, 60s ...
                time.sleep(min(15.0 * (2 ** (consecutive_429 - 1)), 120.0))
            else:
                consecutive_429 = 0
                time.sleep(5.0)

    if not stopped_early:
        status = "success" if failures == 0 and n_ok else ("partial" if n_ok else "failed")
        utils.log_run("fetch_trends", status, n_ok,
                      f"{n_ok} new this run; {already}/{len(tickers)} total saved; "
                      f"{failures} failed")
    return n_ok
