"""
Evaluate Signal A (8-K sentiment) with strict POINT-IN-TIME discipline.

For each 8-K:
  1. Parse EDGAR accepted_datetime (Eastern time).
  2. Determine the FIRST tradable moment strictly AFTER acceptance:
       - We anchor entry to the first price bar with date > acceptance date,
         and measure the h-day forward return from that bar's close. We never
         use the filing day's own close, which for an after-hours 8-K was set
         at or after acceptance.
  3. Forward return over horizon h = close[entry+h] / close[entry] - 1.

WHAT CHANGED, AND WHY
---------------------
1) MARKET ADJUSTMENT. A raw forward return is mostly the market. If a batch
   of 8-Ks lands on a day the index falls 2%, every one of those filings gets
   a large common negative return that has nothing to do with its tone. That
   common component is noise in the numerator of the correlation, so it
   shrinks |IC| toward zero and hides whatever signal is there. We therefore
   also compute an EXCESS return:

       excess = fwd_ret(ticker, h) - bench(entry_date, h)

   where bench is the equal-weighted forward return of every ticker in the
   price universe over the same calendar window. This needs no new data
   source -- the prices are already on disk. It is a crude beta-1 adjustment,
   not a risk model, and is labelled as such.

2) SIGNIFICANCE. An IC without a standard error is not a result. Two are
   reported, because they answer different questions:

   - POOLED: one Spearman across all filings. SE = 1/sqrt(n-1). This assumes
     the observations are independent. THEY ARE NOT -- 8-Ks cluster in
     earnings season, and filings sharing a date share a return shock. The
     pooled t is therefore an UPPER bound on significance, i.e. optimistic.

   - PER-DATE (Fama-MacBeth style): a cross-sectional IC within each entry
     date that has enough filings, then the mean and the SE of that series
     across dates. This is the honest number, because each date contributes
     one observation and the within-date common shock cancels.

   When the two disagree, believe the per-date one.

   Note a consequence that is easy to miss: subtracting the benchmark is
   subtracting the SAME number from every filing that shares an entry date,
   and a rank correlation is invariant to that. So the per-date IC is already
   market-neutral by construction, and market adjustment changes only the
   POOLED number. The two fixes are therefore not independent -- the excess
   return is what lets the pooled estimator approach what the per-date
   estimator already had. A self-check below verifies this holds in the data;
   if it does not, the benchmark has coverage holes.

3) A LOWER GUARD. The existing upper guard flags |IC| > IC_LOOKAHEAD_THRESHOLD
   as a probable lookahead bug. The symmetric failure -- reporting a number
   that is indistinguishable from zero as if it were a finding -- had no
   guard. Rows whose |t| < IC_NOISE_TSTAT are now flagged NOISE.

Output:
  - signals/aligned_returns.csv : per-filing tone, forward and excess returns
  - appends one row per horizon to results/ic_history.csv
"""
from __future__ import annotations

import csv
import datetime as dt
import math
from pathlib import Path

import config
import utils

# Tunables. Read from config if present so config.py need not be edited.
NOISE_TSTAT = getattr(config, "IC_NOISE_TSTAT", 1.96)
MIN_FILINGS_PER_DATE = getattr(config, "IC_MIN_FILINGS_PER_DATE", 5)
MIN_BENCH_TICKERS = getattr(config, "IC_MIN_BENCH_TICKERS", 30)


# --------------------------------------------------------------------------
# prices
# --------------------------------------------------------------------------
def _load_prices(ticker: str) -> list[tuple[dt.date, float]]:
    path = config.PRICES_DIR / f"{ticker}.csv"
    if not path.exists():
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                out.append((dt.date.fromisoformat(r["date"]), float(r["close"])))
            except Exception:
                continue
    out.sort(key=lambda x: x[0])
    return out


def _build_benchmark(horizons) -> dict[int, dict[dt.date, tuple[float, int]]]:
    """Equal-weighted forward return of the whole price universe.

    Returns {horizon: {date: (mean_forward_return, n_tickers)}}.

    Each ticker is anchored to its OWN bar for that date, so a ticker that did
    not trade that day simply does not contribute. Dates covered by fewer than
    MIN_BENCH_TICKERS names are dropped rather than reported thin -- a
    benchmark built from five stocks is not a market.
    """
    sums: dict[int, dict[dt.date, list]] = {h: {} for h in horizons}
    files = sorted(Path(config.PRICES_DIR).glob("*.csv"))
    for path in files:
        series = _load_prices(path.stem)
        if len(series) < 2:
            continue
        dates = [d for d, _ in series]
        closes = [c for _, c in series]
        for i, d in enumerate(dates):
            c0 = closes[i]
            if not c0:
                continue
            for h in horizons:
                j = i + h
                if j >= len(closes):
                    continue
                acc = sums[h].setdefault(d, [0.0, 0])
                acc[0] += closes[j] / c0 - 1.0
                acc[1] += 1

    bench: dict[int, dict[dt.date, tuple[float, int]]] = {}
    for h in horizons:
        bench[h] = {d: (tot / n, n)
                    for d, (tot, n) in sums[h].items()
                    if n >= MIN_BENCH_TICKERS}
    return bench


# --------------------------------------------------------------------------
# time alignment
# --------------------------------------------------------------------------
def _parse_accepted(s: str) -> dt.datetime | None:
    if not s:
        return None
    s = s.replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _entry_index(dates: list[dt.date], accepted: dt.datetime) -> int | None:
    """Index of the first daily bar STRICTLY AFTER the acceptance date.

    Using strictly-after guarantees no use of the filing day's own close,
    which is the key lookahead guard for after-hours 8-Ks."""
    acc_date = accepted.date()
    for i, d in enumerate(dates):
        if d > acc_date:
            return i
    return None


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------
def _spearman(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 3:
        return None

    def rank(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        ranks = [0.0] * len(vals)
        i = 0
        while i < len(vals):
            j = i
            while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[order[k]] = avg
            i = j + 1
        return ranks

    rx, ry = rank(x), rank(y)
    mx = sum(rx) / n
    my = sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def _pooled(x: list[float], y: list[float]) -> dict:
    """Spearman over all filings at once, with an OPTIMISTIC standard error.

    SE = 1/sqrt(n-1) is the large-sample SE of a rank correlation under
    independence. Filings that share a date are not independent, so treat the
    resulting t as a ceiling, not an estimate.
    """
    n = len(x)
    ic = _spearman(x, y)
    if ic is None or n < 4:
        return {"ic": ic, "n": n, "se": None, "t": None, "lo": None, "hi": None}
    se = 1.0 / math.sqrt(n - 1)
    return {"ic": ic, "n": n, "se": se, "t": ic / se,
            "lo": ic - 1.96 * se, "hi": ic + 1.96 * se}


def _per_date(rows: list[tuple[dt.date, float, float]]) -> dict:
    """Fama-MacBeth style: IC within each date, then mean and SE across dates.

    rows: (entry_date, signal, return). Dates with fewer than
    MIN_FILINGS_PER_DATE filings are skipped -- a 3-name cross-section is not
    a cross-section, and including them adds variance, not information.
    """
    by_date: dict[dt.date, list] = {}
    for d, s, r in rows:
        by_date.setdefault(d, []).append((s, r))

    ics = []
    for d, pairs in by_date.items():
        if len(pairs) < MIN_FILINGS_PER_DATE:
            continue
        ic = _spearman([p[0] for p in pairs], [p[1] for p in pairs])
        if ic is not None:
            ics.append(ic)

    k = len(ics)
    if k < 3:
        return {"ic": None, "n_dates": k, "se": None, "t": None}
    mean = sum(ics) / k
    var = sum((v - mean) ** 2 for v in ics) / (k - 1)
    se = math.sqrt(var / k)
    return {"ic": mean, "n_dates": k, "se": se,
            "t": (mean / se if se else None)}


def _r(v, nd=6):
    return "" if v is None else round(v, nd)


# --------------------------------------------------------------------------
# history schema + migration
# --------------------------------------------------------------------------
HIST_FIELDS = [
    "run_time", "signal", "horizon_days", "ic_spearman", "n_obs", "flag",
    # pooled, raw returns
    "ic_se", "ic_tstat", "ic_ci_lo", "ic_ci_hi",
    # pooled, market-adjusted returns
    "ic_excess", "ic_excess_n", "ic_excess_se", "ic_excess_tstat",
    # per-date (Fama-MacBeth) <- the number to believe.
    # Market-neutral by construction, so there is no separate excess version.
    "ic_bydate", "ic_bydate_se", "ic_bydate_tstat", "n_dates",
]


def migrate_history() -> str:
    """Widen an existing ic_history.csv to the new schema, in place.

    Old rows keep their IC and n. SE / t / CI ARE backfilled, because they are
    a deterministic function of (IC, n) -- no new data is invented. The excess
    and per-date columns are left blank for old rows: those genuinely cannot
    be reconstructed without re-running, and a blank says so honestly.
    Idempotent: running it on an already-migrated file is a no-op.
    """
    path = config.IC_HISTORY_CSV
    if not path.exists():
        return "no history file"

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return "history empty"
    if "ic_bydate_tstat" in rows[0]:
        return "already migrated"

    out = []
    for r in rows:
        new = {k: r.get(k, "") for k in HIST_FIELDS}
        try:
            ic = float(r["ic_spearman"])
            n = int(r["n_obs"])
        except (TypeError, ValueError, KeyError):
            out.append(new)
            continue
        if n > 3:
            se = 1.0 / math.sqrt(n - 1)
            t = ic / se
            new["ic_se"] = round(se, 6)
            new["ic_tstat"] = round(t, 3)
            new["ic_ci_lo"] = round(ic - 1.96 * se, 6)
            new["ic_ci_hi"] = round(ic + 1.96 * se, 6)
            if not new["flag"]:
                if abs(ic) > config.IC_LOOKAHEAD_THRESHOLD:
                    new["flag"] = "POSSIBLE_LOOKAHEAD"
                elif abs(t) < NOISE_TSTAT:
                    new["flag"] = "NOISE"
        out.append(new)

    backup = path.with_suffix(".csv.pre_migration")
    if not backup.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HIST_FIELDS)
        w.writeheader()
        w.writerows(out)
    return f"migrated {len(out)} rows (backup: {backup.name})"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def run() -> dict:
    """Align sentiment to point-in-time forward returns and compute IC.

    Returns {horizon: {...}}. The keys "ic" and "n" keep their old meaning
    (pooled, raw) so existing callers are unaffected.
    """
    sent_path = config.SIGNALS_DIR / "sentiment.csv"
    if not sent_path.exists():
        utils.log_run("compute_ic", "failed", 0, "insufficient data (no sentiment.csv)")
        return {}

    horizons = list(config.FORWARD_HORIZONS)
    note = migrate_history()
    if note not in ("already migrated", "no history file"):
        print(f"  ic_history: {note}")

    bench = _build_benchmark(horizons)
    bench_n = {h: len(bench[h]) for h in horizons}
    if not any(bench_n.values()):
        print("  [warn] benchmark empty -- excess returns unavailable "
              f"(need >= {MIN_BENCH_TICKERS} tickers priced per date)")

    price_cache: dict[str, list[tuple[dt.date, float]]] = {}
    aligned = []

    with open(sent_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ticker = r["ticker"]
            accepted = _parse_accepted(r.get("accepted_datetime", ""))
            if accepted is None:
                continue  # cannot place in time -> skip (never guess)
            if ticker not in price_cache:
                price_cache[ticker] = _load_prices(ticker)
            series = price_cache[ticker]
            if not series:
                continue
            dates = [d for d, _ in series]
            closes = [c for _, c in series]
            ei = _entry_index(dates, accepted)
            if ei is None:
                continue
            entry_date = dates[ei]
            row = {
                "ticker": ticker,
                "accession": r["accession"],
                "accepted_datetime": r["accepted_datetime"],
                "entry_date": entry_date.isoformat(),
                "tone": float(r["tone"]),
            }
            entry_close = closes[ei]
            has_any = False
            for h in horizons:
                j = ei + h
                if j < len(closes) and entry_close:
                    fwd = closes[j] / entry_close - 1.0
                    row[f"fwd_ret_{h}d"] = fwd
                    b = bench.get(h, {}).get(entry_date)
                    if b is None:
                        row[f"bench_ret_{h}d"] = ""
                        row[f"exc_ret_{h}d"] = ""
                    else:
                        row[f"bench_ret_{h}d"] = b[0]
                        row[f"exc_ret_{h}d"] = fwd - b[0]
                    has_any = True
                else:
                    row[f"fwd_ret_{h}d"] = ""      # insufficient data
                    row[f"bench_ret_{h}d"] = ""
                    row[f"exc_ret_{h}d"] = ""
            if has_any:
                aligned.append(row)

    # Persist the aligned panel.
    config.SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["ticker", "accession", "accepted_datetime", "entry_date", "tone"]
    for h in horizons:
        fields += [f"fwd_ret_{h}d", f"bench_ret_{h}d", f"exc_ret_{h}d"]
    with open(config.SIGNALS_DIR / "aligned_returns.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in aligned:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v)
                        for k, v in row.items()})

    # Compute IC per horizon and append to ic_history.csv.
    results = {}
    run_time = utils.utcnow_iso()
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    new_hist = not config.IC_HISTORY_CSV.exists()
    with open(config.IC_HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HIST_FIELDS)
        if new_hist:
            w.writeheader()

        for h in horizons:
            raw_rows, exc_rows = [], []
            for row in aligned:
                d = dt.date.fromisoformat(row["entry_date"])
                v = row.get(f"fwd_ret_{h}d")
                if isinstance(v, float):
                    raw_rows.append((d, row["tone"], v))
                e = row.get(f"exc_ret_{h}d")
                if isinstance(e, float):
                    exc_rows.append((d, row["tone"], e))

            p_raw = _pooled([r[1] for r in raw_rows], [r[2] for r in raw_rows])
            p_exc = _pooled([r[1] for r in exc_rows], [r[2] for r in exc_rows])
            d_raw = _per_date(raw_rows)
            d_exc = _per_date(exc_rows)

            # Flag. The lookahead guard dominates -- a |IC| that large with a
            # small t only happens on a tiny sample, and the bug matters more.
            # Emitted as a single token so existing self-checks still match.
            flag = ""
            ics = [v for v in (p_raw["ic"], p_exc["ic"]) if v is not None]
            if any(abs(v) > config.IC_LOOKAHEAD_THRESHOLD for v in ics):
                flag = "POSSIBLE_LOOKAHEAD"
            else:
                # Judge on the most conservative statistic available.
                t = next((x for x in (d_raw["t"], p_exc["t"], p_raw["t"])
                          if x is not None), None)
                if t is not None and abs(t) < NOISE_TSTAT:
                    flag = "NOISE"

            w.writerow({
                "run_time": run_time, "signal": "8k_sentiment",
                "horizon_days": h,
                "ic_spearman": _r(p_raw["ic"]), "n_obs": p_raw["n"], "flag": flag,
                "ic_se": _r(p_raw["se"]), "ic_tstat": _r(p_raw["t"], 3),
                "ic_ci_lo": _r(p_raw["lo"]), "ic_ci_hi": _r(p_raw["hi"]),
                "ic_excess": _r(p_exc["ic"]), "ic_excess_n": p_exc["n"],
                "ic_excess_se": _r(p_exc["se"]),
                "ic_excess_tstat": _r(p_exc["t"], 3),
                "ic_bydate": _r(d_raw["ic"]), "ic_bydate_se": _r(d_raw["se"]),
                "ic_bydate_tstat": _r(d_raw["t"], 3),
                "n_dates": d_raw["n_dates"],
            })

            results[h] = {"ic": p_raw["ic"], "n": p_raw["n"],
                          "se": p_raw["se"], "t": p_raw["t"],
                          "ci": (p_raw["lo"], p_raw["hi"]),
                          "ic_excess": p_exc["ic"], "t_excess": p_exc["t"],
                          "ic_bydate": d_raw["ic"], "t_bydate": d_raw["t"],
                          "n_dates": d_raw["n_dates"], "flag": flag}

            # Self-check: per-date IC is invariant to subtracting a constant
            # per date, so the raw and excess per-date ICs must agree. A gap
            # means some filings lost their benchmark and the two runs are on
            # different samples -- i.e. thin benchmark coverage.
            if (d_raw["ic"] is not None and d_exc["ic"] is not None
                    and abs(d_raw["ic"] - d_exc["ic"]) > 1e-9):
                print(f"  [check] {h}d: per-date IC differs raw vs excess "
                      f"({d_raw['ic']:+.4f} vs {d_exc['ic']:+.4f}) -- "
                      f"benchmark coverage is incomplete "
                      f"({d_raw['n_dates']} vs {d_exc['n_dates']} dates)")

    _print_summary(results, bench_n, horizons)

    n_total = len(aligned)
    status = "success" if n_total else "partial"
    utils.log_run("compute_ic", status, n_total,
                  f"{n_total} aligned filings; IC + significance per horizon")
    return results


def _fmt(v, nd=4):
    return " n/a  " if v is None else f"{v:+.{nd}f}"


def _print_summary(results, bench_n, horizons) -> None:
    print("\n  IC with significance (8-K sentiment)")
    print("  benchmark coverage: "
          + ", ".join(f"{h}d={bench_n.get(h, 0)} dates" for h in horizons))
    print("  " + "-" * 72)
    print(f"  {'h':>3} {'pooled raw':>12} {'t':>7} {'pooled exc':>12} {'t':>7}"
          f" {'by-date':>12} {'t':>7} {'N':>5} {'flag':>6}")
    for h in sorted(results):
        d = results[h]
        print(f"  {h:>3}d {_fmt(d['ic']):>12} {_fmt(d['t'],2):>7}"
              f" {_fmt(d['ic_excess']):>12} {_fmt(d['t_excess'],2):>7}"
              f" {_fmt(d['ic_bydate']):>12}"
              f" {_fmt(d['t_bydate'],2):>7} {d['n_dates']:>5} {d['flag'] or '-':>6}")
    print("  " + "-" * 72)
    print("  pooled t assumes independent filings and is optimistic;")
    print(f"  by-date t is the one to believe. |t| < {NOISE_TSTAT} -> NOISE.\n")
