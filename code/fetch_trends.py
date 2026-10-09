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
import datetime as dt
import time
from pathlib import Path

import config
import utils

# Google Trends throttles aggressively (HTTP 429). To stay a good citizen and
# keep coverage current, each run fetches at most MAX_PER_RUN tickers: first
# tickers never fetched, then the stalest files (oldest latest-week first).
# A file is stale once its newest week is more than STALE_DAYS old, so the
# whole universe is refreshed about once a week across daily runs.
MAX_PER_RUN = 120             # ~12 minutes at BASE_DELAY_SEC
BASE_DELAY_SEC = 6.0          # spacing between successful requests
MAX_CONSECUTIVE_429 = 4       # stop the run after this many 429s in a row
STALE_DAYS = 7

VINTAGE_DIR = config.DATA_DIR / "trends_vintages"


def _is_rate_limited(exc: Exception) -> bool:
    return "429" in str(exc)


def _latest_week(path: Path) -> dt.date | None:
    last = None
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                last = r.get("week") or last
        return dt.date.fromisoformat(last) if last else None
    except Exception:  # noqa: BLE001
        return None


def _record_vintage(tk: str, weeks: list[tuple[str, int]], retrieved: dt.date) -> None:
    """Append the newest CLOSED weeks of this pull to a vintage log.

    Google rescales the whole series on every request, so a value stored in
    data/trends/<TK>.csv is the latest revision, not what was knowable at the
    time. The vintage log keeps, per retrieval date, the two most recent weeks
    that had already closed: their ratio is exactly what a model could have
    computed on that date (point-in-time), and trends_factor.py prefers it.
    """
    closed = [(w, v) for w, v in weeks
              if dt.date.fromisoformat(w) + dt.timedelta(days=7) <= retrieved]
    if len(closed) < 2:
        return
    VINTAGE_DIR.mkdir(parents=True, exist_ok=True)
    out = VINTAGE_DIR / f"{tk}.csv"
    new = not out.exists()
    with open(out, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["retrieved", "week", "interest"])
        for wk, val in closed[-2:]:
            w.writerow([retrieved.isoformat(), wk, val])


def run(tickers: list[str], name_map: dict[str, str] | None = None) -> int:
    """Fetch weekly interest for each ticker's company name.

    New tickers first, then the stalest files; at most MAX_PER_RUN per run,
    with backoff and an early stop on rate limits. Returns tickers fetched.
    """
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

    today = dt.date.today()
    missing = [tk for tk in tickers if not (config.TRENDS_DIR / f"{tk}.csv").exists()]
    ages = []
    for tk in tickers:
        p = config.TRENDS_DIR / f"{tk}.csv"
        if p.exists():
            lw = _latest_week(p)
            if lw is None or (today - lw).days > STALE_DAYS:
                ages.append((lw or dt.date.min, tk))
    stale = [tk for _, tk in sorted(ages)]
    batch = (missing + stale)[:MAX_PER_RUN]
    if not batch:
        utils.log_run("fetch_trends", "success", 0,
                      f"up to date: {len(tickers)}/{len(tickers)} files newer than {STALE_DAYS} days")
        return 0

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
            weeks = [(idx.strftime("%Y-%m-%d"), int(val)) for idx, val in df[term].items()]
            out = config.TRENDS_DIR / f"{tk}.csv"
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["week", "interest"])
                w.writerows(weeks)
            _record_vintage(tk, weeks, today)
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
                      f"{n_ok} fetched ({len(missing)} new, {len(stale)} stale queued); "
                      f"{failures} failed")
    return n_ok
