"""
Orchestrator for the 8-K Sentiment + Google Trends signal pipeline.

Self-bootstrapping run-state detection:
  - FIRST RUN (run_log.csv has only a header / missing): perform ONE-TIME
    SETUP -- expand universe toward S&P 500, resolve CIKs, backfill ~6 months
    of 8-Ks and ~2 years of prices, pull initial Google Trends, compute
    sentiment + trends factor + IC.
  - OTHERWISE: incremental update since the last successful run.

Every stage is wrapped in try/except: failures are logged, partials saved,
and the project is always left resumable. Self-checks run at the end.

Usage:
  python run_pipeline.py            # auto-detect first vs incremental
  python run_pipeline.py --setup    # force one-time setup
  python run_pipeline.py --no-trends  # skip Google Trends (e.g. if blocked)
  python run_pipeline.py --no-text    # skip downloading 8-K body text
"""
from __future__ import annotations

import argparse
import csv
import sys

import requests

import config
import utils
import build_universe
import fetch_prices
import fetch_8k
import fetch_trends
import sentiment
import trends_factor
import compute_ic


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": config.SEC_USER_AGENT})
    return s


def _stage(name, fn, *args, **kwargs):
    """Run a stage; log + swallow errors so the pipeline continues."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        utils.log_run(name, "failed", 0, str(exc))
        print(f"[stage failed] {name}: {exc}", file=sys.stderr)
        return None


def self_checks() -> list[str]:
    """Scan recent run_log rows and ic_history for warning conditions."""
    warnings = []
    # 1) Repeated stage failures in the last 5 rows.
    if config.RUN_LOG_CSV.exists():
        with open(config.RUN_LOG_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        last5 = rows[-5:]
        failed = [r for r in last5 if r.get("status") == "failed"]
        by_stage = {}
        for r in failed:
            by_stage[r["stage"]] = by_stage.get(r["stage"], 0) + 1
        for stage, c in by_stage.items():
            if c >= 2:
                warnings.append(f"Stage '{stage}' failed {c}x in last 5 runs.")
    # 2) |IC| persistently above threshold -> likely lookahead.
    if config.IC_HISTORY_CSV.exists():
        with open(config.IC_HISTORY_CSV, newline="", encoding="utf-8") as f:
            hist = list(csv.DictReader(f))
        flagged = [h for h in hist[-6:] if h.get("flag") == "POSSIBLE_LOOKAHEAD"]
        if flagged:
            warnings.append(
                f"|IC| exceeded {config.IC_LOOKAHEAD_THRESHOLD} in "
                f"{len(flagged)} recent rows -- POSSIBLE LOOKAHEAD (check bugs).")
    return warnings


def main() -> None:
    stage_keys = ["prices", "filings", "trends", "sentiment", "trends_factor", "ic"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true", help="force one-time setup")
    ap.add_argument("--no-trends", action="store_true", help="skip Google Trends")
    ap.add_argument("--no-text", action="store_true", help="skip 8-K body text")
    ap.add_argument(
        "--only", default="",
        help=("comma-separated stages to run instead of the full pipeline. "
              "Choices: " + ", ".join(stage_keys) + ". 'signals' is shorthand "
              "for sentiment,trends_factor,ic. Universe is always loaded first. "
              "Example: --only prices  or  --only signals"))
    args = ap.parse_args()

    # Resolve which stages to run.
    if args.only:
        requested = set()
        for tok in args.only.split(","):
            tok = tok.strip().lower()
            if tok == "signals":
                requested.update({"sentiment", "trends_factor", "ic"})
            elif tok in stage_keys:
                requested.add(tok)
            elif tok:
                print(f"[warn] unknown stage '{tok}' ignored", file=sys.stderr)
    else:
        requested = set(stage_keys)

    def wanted(k):
        return k in requested

    utils.ensure_dirs()
    session = _session()

    is_first_run = args.setup or not utils.run_log_has_real_data()
    mode = ("ONE-TIME SETUP" if is_first_run else "INCREMENTAL UPDATE")
    if args.only:
        mode += f" (--only {','.join(sorted(requested))})"
    print(f"=== Pipeline run: {mode} ===")
    utils.log_run("run_start", "success", 0, mode)

    # Universe + CIKs: always needed for the ticker list. Expand to S&P 500
    # only on a first full run (not when re-running a single stage).
    expand = is_first_run and not args.only
    universe = _stage("build_universe", build_universe.run, session, expand=expand)
    if not universe:
        universe = build_universe.load_universe()  # fall back to whatever exists

    name_map = {r["ticker"]: r.get("company", r["ticker"]) for r in universe}
    tickers = [r["ticker"] for r in universe]

    if wanted("prices"):
        _stage("fetch_prices", fetch_prices.run, session, tickers)

    if wanted("filings"):
        _stage("fetch_8k", fetch_8k.run, session, universe, fetch_text=not args.no_text)

    if wanted("trends") and not args.no_trends:
        _stage("fetch_trends", fetch_trends.run, tickers, name_map)

    if wanted("sentiment"):
        _stage("sentiment", sentiment.run)
    if wanted("trends_factor"):
        _stage("trends_factor", trends_factor.run)

    ic = {}
    if wanted("ic"):
        ic = _stage("compute_ic", compute_ic.run) or {}

    utils.log_run("run_end", "success", len(tickers), mode)

    # Self-checks.
    warnings = self_checks()
    print("\n=== Self-checks ===")
    if warnings:
        for w in warnings:
            print("  ⚠️", w)
    else:
        print("  none")

    print("\n=== IC summary (8-K sentiment) ===")
    for h, d in sorted(ic.items()):
        ic_val = d.get("ic")
        print(f"  horizon {h}d: IC={'n/a' if ic_val is None else round(ic_val,4)} "
              f"(n={d.get('n')})")
    print("\nDone. See results/run_log.csv, results/ic_history.csv, signals/.")


if __name__ == "__main__":
    main()
