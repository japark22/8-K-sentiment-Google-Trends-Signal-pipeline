# 8-K Sentiment + Google Trends Signal Pipeline

A reproducible research pipeline that turns two **public** alternative-data
sources into predictive equity signals and validates them honestly:

- **Signal A** — SEC 8-K filing sentiment (EDGAR)
- **Signal B** — Google Trends search interest

Public data only. Strict point-in-time discipline. No fabricated numbers.
See [`PIPELINE_NOTES.md`](PIPELINE_NOTES.md) for methodology and limitations.

## Design highlights

- **Point-in-time correctness by construction.** Every 8-K is anchored to its
  EDGAR `acceptanceDateTime`, and forward returns start from the first price
  bar *strictly after* that moment — never the filing day's own close. This is
  the single most common backtest bug, and it is prevented explicitly.
- **Honest validation, not curve-fitting.** Signal quality is measured with
  rank IC. A built-in guardrail flags `|IC| > 0.30` as a *likely lookahead bug,
  not skill* — the pipeline is designed to catch its own optimism.
- **Reproducible and resumable.** Every stage logs to an append-only audit
  trail, retries with exponential backoff, and saves partial results so a run
  can always resume. No hidden state.
- **Documented limitations.** Survivorship bias, lexicon choice, and Google
  Trends rescaling are disclosed rather than hidden.
- **Public data only.** SEC EDGAR, public prices, Google Trends — fully
  reproducible by anyone.

## Results (latest run — 2026-08-17)

Coverage: 503 S&P 500 names (CIKs resolved), 503/503 tickers with daily prices
(~249k bars over ~2 years), and ~3,560 8-K filings scored over a ~6-month window
(3,531 aligned to point-in-time forward returns).

Signal A — 8-K sentiment tone vs. point-in-time forward returns (Spearman rank
IC; entry = first trading day strictly after each filing's EDGAR
`acceptanceDateTime`):

| Horizon | Rank IC | Observations |
|--------:|--------:|-------------:|
| 1 day   | −0.0171 |        3,531 |
| 3 days  | −0.0030 |        3,479 |
| 5 days  | −0.0037 |        3,434 |

All three ICs are near zero and none trip the `|IC| > 0.30` lookahead guard —
an honest, believable result for a simple 8-K tone signal, and evidence that
the point-in-time construction is not leaking future information. These numbers
use the built-in **baseline** lexicon; supplying the full Loughran-McDonald
dictionary (`data/lm_master_dictionary.csv`) is the natural next step. **Signal
B (Google Trends) has not been backfilled yet**, so its factor is currently
empty. Numbers trace to `results/ic_history.csv` and `signals/`.

## Layout

```
code/                 pipeline modules (see below)
data/
  universe.csv        investable universe (ticker, company, cik)
  prices/             daily OHLC per ticker (<TICKER>.csv)
  filings_8k/         8-K metadata per ticker + text/ bodies
  trends/             weekly Google Trends interest per ticker
signals/              sentiment.csv, trends_factor.csv, aligned_returns.csv
results/
  run_log.csv         append-only audit log of every stage
  ic_history.csv      IC per horizon per run (with lookahead flag)
reports/{ops,weekly}  generated reports
```

## Setup

Homebrew's Python is externally managed (PEP 668), so use an isolated virtual
environment — the clean, recommended approach:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r code/requirements.txt
```

Optionally set a contact email for SEC's required User-Agent (defaults are set):

```bash
export SEC_CONTACT_EMAIL="you@example.com"
```

## Run

With the virtual environment activated (`source .venv/bin/activate`):

```bash
python code/run_pipeline.py            # auto: first-run setup vs incremental
python code/run_pipeline.py --setup    # force one-time backfill
python code/run_pipeline.py --no-trends  # skip Google Trends if it blocks you
```

## Scheduled pipeline (hands-off, via macOS launchd)

`code/run_auto.sh` activates the venv, runs the incremental pipeline, and
commits + pushes results to GitHub. `schedule/local.8ktrends.plist`
schedules it on weekdays at 18:00 local time. Install once:

```bash
bash schedule/install.sh
```

It then runs unattended (while the Mac is awake and you are logged in; a run
missed due to sleep/shutdown fires at the next opportunity). Progress is logged
to `results/pipeline.log`. To stop it:
`bash schedule/install.sh --uninstall`.

The first run performs the one-time backfill (expand universe toward the
S&P 500, ~6 months of 8-Ks, ~2 years of prices, initial Trends) and computes
baseline sentiment, the trends factor, and IC. Subsequent runs update
incrementally. The pipeline is resumable: failures are logged and partials are
saved.

## Modules

| File | Purpose |
|------|---------|
| `config.py` | Paths, SEC User-Agent, windows, thresholds |
| `utils.py` | Run logging, throttling, retry w/ backoff, state detection |
| `build_universe.py` | Expand to S&P 500, resolve CIKs from SEC |
| `fetch_prices.py` | Daily prices from Yahoo Finance via yfinance (public, key-free, batched) |
| `fetch_8k.py` | 8-K metadata + text; captures `acceptanceDateTime` |
| `fetch_trends.py` | Google Trends via pytrends (throttled/batched) |
| `sentiment.py` | Signal A: LM-lexicon tone per 8-K |
| `trends_factor.py` | Signal B: lagged week-over-week interest |
| `compute_ic.py` | Point-in-time forward returns + Spearman IC |
| `run_pipeline.py` | Orchestrator w/ state detection & self-checks |
```
```

## Data & GitHub

The repository is kept lightweight: **bulk raw data is not committed** — it is
fully regenerable by running the pipeline. Only code, the universe, signal
outputs, results/logs, reports, and a few small format examples in
`data/sample/` are tracked. Running the pipeline repopulates `data/prices/`,
`data/filings_8k/`, and `data/trends/` locally (these are git-ignored).
