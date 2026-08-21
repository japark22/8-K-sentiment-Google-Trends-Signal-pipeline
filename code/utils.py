"""
Shared utilities: run logging, throttling, and retrying HTTP requests.

These implement the project's ERROR HANDLING and RESPECT-SOURCES rules:
retries with exponential backoff, request throttling, and an append-only
run_log.csv so every run is auditable and resumable.
"""
from __future__ import annotations

import csv
import time
import datetime as dt
from pathlib import Path
from typing import Optional

import config

_last_request_ts = {"sec": 0.0}


def utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dirs() -> None:
    for d in (config.PRICES_DIR, config.FILINGS_DIR, config.TRENDS_DIR,
              config.SIGNALS_DIR, config.RESULTS_DIR,
              config.REPORTS_DIR / "ops", config.REPORTS_DIR / "weekly"):
        Path(d).mkdir(parents=True, exist_ok=True)


def log_run(stage: str, status: str, count: int = 0, error_summary: str = "") -> None:
    """Append one row to results/run_log.csv.

    status is one of: success | partial | failed
    """
    config.RUN_LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
    new_file = not config.RUN_LOG_CSV.exists()
    # Keep error summaries single-line and short so the CSV stays clean.
    error_summary = (error_summary or "").replace("\n", " ").replace("\r", " ")[:300]
    with open(config.RUN_LOG_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["run_time", "stage", "status", "count", "error_summary"])
        w.writerow([utcnow_iso(), stage, status, count, error_summary])


def throttle(key: str = "sec", min_interval: Optional[float] = None) -> None:
    """Sleep so consecutive requests for `key` respect a minimum interval."""
    interval = config.SEC_MIN_INTERVAL_SEC if min_interval is None else min_interval
    now = time.monotonic()
    elapsed = now - _last_request_ts.get(key, 0.0)
    if elapsed < interval:
        time.sleep(interval - elapsed)
    _last_request_ts[key] = time.monotonic()


def get_with_retry(session, url, *, headers=None, params=None, key="sec",
                   min_interval=None, timeout=None):
    """GET with throttling + exponential backoff (up to MAX_RETRIES).

    Returns the successful requests.Response, or raises the last exception.
    Honors HTTP 429 / 503 by backing off. Never silently fabricates data.
    """
    timeout = config.REQUEST_TIMEOUT_SEC if timeout is None else timeout
    last_exc = None
    for attempt in range(config.MAX_RETRIES):
        try:
            throttle(key=key, min_interval=min_interval)
            resp = session.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code in (429, 503):
                raise RuntimeError(f"rate-limited HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001 - we retry all transient errors
            last_exc = exc
            wait = config.BACKOFF_BASE_SEC ** (attempt + 1)
            time.sleep(wait)
    raise last_exc if last_exc else RuntimeError(f"failed GET {url}")


def last_successful_run(stage: Optional[str] = None) -> Optional[str]:
    """Return run_time of the most recent successful (or partial) run,
    optionally filtered by stage. Used for incremental updates."""
    if not config.RUN_LOG_CSV.exists():
        return None
    best = None
    with open(config.RUN_LOG_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") not in ("success", "partial"):
                continue
            if stage and row.get("stage") != stage:
                continue
            best = row.get("run_time") or best
    return best


def run_log_has_real_data() -> bool:
    """First-run detection: True if run_log.csv has any data rows."""
    if not config.RUN_LOG_CSV.exists():
        return False
    with open(config.RUN_LOG_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return len(rows) > 1  # more than just the header
