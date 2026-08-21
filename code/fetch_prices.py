"""
Fetch daily price history from a PUBLIC, key-free source (Yahoo Finance via
the `yfinance` library).

Stored per ticker at data/prices/<TICKER>.csv with columns:
date, open, high, low, close, volume  (date ascending).

Prices are split/dividend adjusted (auto_adjust=True), the standard basis for
computing returns. NOTE (documented in PIPELINE_NOTES.md): adjusted prices
embed later corporate actions; over the short 1-5 day forward horizons used
here the effect is negligible and does not change the sign of returns.

POINT-IN-TIME NOTE: forward returns in compute_ic.py are always measured from
the FIRST trading day strictly AFTER a filing's EDGAR accepted_datetime --
never the filing date's own close.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import config
import utils

BATCH_SIZE = 50  # tickers per yfinance download call (gentle + efficient)


def _write_ticker(ticker: str, records: list[dict]) -> None:
    out = config.PRICES_DIR / f"{ticker}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume"])
        w.writeheader()
        w.writerows(records)


def _extract(df, ticker: str, multi: bool):
    """Return a cleaned list of daily records for one ticker, or [] if none."""
    import pandas as pd  # local import; provided by yfinance dependency

    if multi:
        # Multi-ticker download -> columns are a (ticker, field) MultiIndex.
        if ticker not in df.columns.get_level_values(0):
            return []
        sub = df[ticker]
    else:
        sub = df

    sub = sub.dropna(how="all")
    records = []
    for idx, row in sub.iterrows():
        close = row.get("Close")
        if close is None or pd.isna(close):
            continue
        d = idx.date() if hasattr(idx, "date") else idx

        def _num(v):
            return "" if (v is None or pd.isna(v)) else round(float(v), 6)

        records.append({
            "date": d.isoformat(),
            "open": _num(row.get("Open")),
            "high": _num(row.get("High")),
            "low": _num(row.get("Low")),
            "close": _num(close),
            "volume": "" if pd.isna(row.get("Volume")) else int(row.get("Volume")),
        })
    return records


def run(session, tickers: list[str]) -> tuple[int, int]:
    """Fetch prices for all tickers in batches. Returns (n_ok, n_rows_total).
    Continues past per-ticker/batch failures; logs a partial/success summary.
    `session` is accepted for interface consistency but unused (yfinance
    manages its own HTTP)."""
    try:
        import yfinance as yf
    except Exception as exc:  # noqa: BLE001
        utils.log_run("fetch_prices", "failed", 0, f"yfinance not installed: {exc}")
        return 0, 0

    start = (dt.date.today() - dt.timedelta(days=config.PRICES_LOOKBACK_DAYS)).isoformat()
    end = (dt.date.today() + dt.timedelta(days=1)).isoformat()

    n_ok, n_rows, failures = 0, 0, 0
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        try:
            df = yf.download(
                batch, start=start, end=end, interval="1d",
                auto_adjust=True, group_by="ticker", threads=True,
                progress=False,
            )
        except Exception as exc:  # noqa: BLE001
            failures += len(batch)
            utils.log_run("fetch_prices_batch", "failed", 0,
                          f"batch {i//BATCH_SIZE}: {exc}")
            continue

        if df is None or len(df) == 0:
            failures += len(batch)
            utils.log_run("fetch_prices_batch", "failed", 0,
                          f"batch {i//BATCH_SIZE}: insufficient data (empty)")
            continue

        multi = len(batch) > 1
        for tk in batch:
            try:
                records = _extract(df, tk, multi)
                if not records:
                    raise RuntimeError("insufficient data (no rows)")
                _write_ticker(tk, records)
                n_ok += 1
                n_rows += len(records)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                utils.log_run("fetch_prices_ticker", "failed", 0, f"{tk}: {exc}")

    status = "success" if failures == 0 and n_ok else ("partial" if n_ok else "failed")
    utils.log_run("fetch_prices", status, n_ok,
                  f"{n_ok}/{len(tickers)} tickers, {n_rows} rows, {failures} failed")
    return n_ok, n_rows
