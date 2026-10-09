# 8-K Sentiment + Google Trends Signal Pipeline

**Do two public alternative-data signals predict S&P 500 returns once the backtest is made honest? A daily, point-in-time pipeline, and a result that says exactly how much the sample can and cannot resolve.**

- **Signal A:** tone of SEC 8-K filings, scored with the Loughran-McDonald lexicon.
- **Signal B:** week-over-week change in Google Trends search interest for each company.

Public data only (SEC EDGAR, Yahoo Finance prices, Google Trends). The pipeline runs every weekday on GitHub Actions and commits its results here.

## Research at a glance

**Question.** Do these signals carry information about short-horizon returns that survives a strictly point-in-time construction and correct standard errors?

**What makes the test honest**

1. **Timing.** Every 8-K is anchored to its EDGAR `acceptanceDateTime`, not its filing date. The forward return starts at the first close strictly after that moment, never at a price set before the news was public. A Trends value enters only once its week has closed.
2. **Statistics.** Pooling filings with SE = 1/√(n−1) treats filings that share a date as independent. On this data it once reported t = +2.19 where the correct by-date estimator gave t = +0.50. Every headline number below is a by-date (Fama-MacBeth) IC.
3. **Power, stated up front.** With about 120 entry dates the sample can resolve |IC| above roughly 0.045. Tone effects reported in the literature are 0.01–0.03. A null here is "too small to see", not "zero", and the report says so ([`reports/findings_8k_sentiment.md`](reports/findings_8k_sentiment.md)).
4. **Revisions in Google Trends.** Google rescales a series on every request. From now on each refresh logs a dated vintage, and the factor prefers the value as it looked on that date. History older than the vintage log is labelled as revision-prone.
5. **No silent method changes.** The scheduled job refuses to run without the full LM lexicon rather than falling back to a toy word list. It flags any |IC| above 0.30 as a likely lookahead bug.

**Results.** The numbers trace to [`results/ic_history.csv`](results/ic_history.csv) and [`results/trends_ic_history.csv`](results/trends_ic_history.csv).

Signal A, 8-K tone vs market-adjusted forward return (S&P 500, run of 2026-10-08):

| Horizon | By-date IC | t | Entry dates | Filings |
|--------:|-----------:|--:|------------:|--------:|
| 1 day | +0.0282 | 1.25 | 124 | 3,352 |
| 3 days | +0.0161 | 0.74 | 122 | 3,316 |
| 5 days | +0.0056 | 0.24 | 120 | 3,278 |

Signal B, Trends week-over-week change vs 5-day excess return: weekly IC **+0.0166, t = 1.57**, over 60 weeks and 25,944 ticker-weeks (2025-07 to 2026-08). This was computed on the full Trends set collected before the move to GitHub Actions. The runner rebuilds its own Trends store at about 100 names a day under Google's rate limit, and any IC computed on less than 90% of the universe is logged as `partial`, with its `coverage` recorded. None of these weeks rests on vintages yet, since vintage logging starts with the scheduled runs.

**Reading.** Both signals are positive and small, and neither is statistically distinguishable from zero. That is consistent with the literature's effect sizes and with the sample's stated resolution. Breaking results down by 8-K item, with a Bonferroni threshold of |t| > 2.99 across 18 tests, found nothing ([`results/ic_by_item_full.txt`](results/ic_by_item_full.txt)). The intraday timing decomposition shows no tradable drift that the close-to-close numbers miss ([`results/timing_decomposition.txt`](results/timing_decomposition.txt)).

**Extension, Korea.** Applying the same design to 259,541 DART disclosure titles gives a small positive market-adjusted IC that rises with horizon (0.017 at 1 day to 0.034 at 5 days) and is positive in both years ([`reports/apac_kr_phase1.md`](reports/apac_kr_phase1.md)).

---

## How it runs

```
GitHub Actions, weekdays 10:05 UTC (.github/workflows/pipeline.yml)
  restore raw data (Actions cache)  ->  universe + CIKs (SEC)  ->  prices (yfinance)
  ->  8-K metadata + text (EDGAR, <=2.5 req/s)  ->  Trends refresh (new, then stalest; vintage log)
  ->  sentiment  ->  trends factor  ->  IC (Signal A)  ->  IC (Signal B)
  ->  commit signals/ results/ data/trends_vintages/  ->  fail the job (e-mail) if a core stage failed
```

Every stage appends to [`results/run_log.csv`](results/run_log.csv) (`success` / `partial` / `failed`). Requests retry with exponential backoff, and a blocked source saves partial results so the next run resumes. Bulk raw data (prices, 8-K texts, Trends series) is not tracked in git. It persists between runs in the Actions cache, and a cache miss only means refetching.

**Secrets the job needs** (repository Settings → Secrets → Actions):

- `SEC_CONTACT_EMAIL`: the contact address SEC's fair-access policy asks for in the User-Agent.
- `LM_WORDLISTS`: the positive and negative LM word lists, packed from your own copy of the Master Dictionary. The dictionary itself is never redistributed here.

## Layout

```
code/
  run_pipeline.py      orchestrator: state detection, stages, self-checks
  build_universe.py    S&P 500 universe, CIKs from SEC's own ticker files
  fetch_prices.py      daily prices (yfinance, batched)
  fetch_8k.py          8-K metadata + text, keyed on acceptanceDateTime
  fetch_trends.py      Google Trends refresh with point-in-time vintages
  sentiment.py         Signal A: LM tone per filing
  trends_factor.py     Signal B: week-over-week change, closed weeks only
  compute_ic.py        Signal A evaluation: pooled, excess and by-date IC
  compute_trends_ic.py Signal B evaluation: weekly cross-sectional IC
  ic_by_item.py, decompose_timing.py   follow-up analyses
  fetch_dart_kr.py, fetch_kr_prices.py, signal_kr.py, eval_kr.py   Korea extension
  probes/              the two one-off probes behind the exhibit-parsing decision
data/
  universe.csv         ticker, company, CIK
  trends_vintages/     dated Trends values (point-in-time record, tracked)
  sample/              small format examples of the untracked raw stores
signals/               sentiment.csv, trends_factor.csv, aligned_returns.csv
results/               run_log.csv, ic_history.csv, trends_ic_history.csv, item and timing tables
reports/               findings, Korea extension, ops self-checks, weekly reports
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r code/requirements.txt
export SEC_CONTACT_EMAIL="you@example.com"
python code/run_pipeline.py              # first run backfills; later runs are incremental
python code/run_pipeline.py --only signals   # recompute sentiment, factors and IC from data on disk
python code/run_pipeline.py --no-trends      # skip Google Trends
```

For the full lexicon, place the Loughran-McDonald Master Dictionary at `data/lm_master_dictionary.csv` (free for academic use from [SRAF](https://sraf.nd.edu/loughranmcdonald-master-dictionary/)). Without it a small placeholder list is used and labelled as such. `code/run_auto.sh` and `schedule/` hold the earlier macOS launchd setup, kept for running on a local machine instead.

## Limitations

- **Survivorship.** The universe is current S&P 500 membership, applied backwards.
- **Short history.** Six months of 8-Ks and a twelve-month Trends window. The power statement above is the binding constraint.
- **Crude market adjustment.** It subtracts an equal-weighted market return. It is not a risk model.
- **Revision-prone Trends history.** Trends history before the vintage log began uses revised values.

See [`PIPELINE_NOTES.md`](PIPELINE_NOTES.md) for methodology details.
