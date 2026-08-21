# Pipeline Notes — Methodology & Known Limitations

This project turns two **public** alternative-data sources into predictive
equity signals and validates them honestly:

- **Signal A — 8-K filing sentiment** (SEC EDGAR)
- **Signal B — Google Trends** search interest

All data is public: SEC EDGAR, public daily prices (Yahoo Finance via
yfinance), and Google Trends.
No proprietary data, code, lists, parameters, or methodology is used.

## Point-in-time discipline (the most important rule)

A signal at time *T* may use only information public at time *T*.

**8-K sentiment.** Each filing is anchored to its EDGAR `acceptanceDateTime`
(the moment it became public), *not* the filing date alone. Forward returns are
measured from the **first daily price bar strictly after the acceptance date**.
Using "strictly after" guarantees we never use the filing day's own close,
which for after-hours 8-Ks is set at/after the acceptance moment — the classic
lookahead trap. See `code/compute_ic.py` (`_entry_index`).

**Google Trends.** Only values for weeks that have already closed inform a
signal. The trends factor for the start of week *W* uses the change between
weeks *W-2* and *W-1* (both fully public before *W*). See
`code/trends_factor.py` (`factor_asof`).

**Lookahead guard.** Information coefficient (IC) is Spearman rank correlation
between the signal and forward returns. If `|IC|` stays above **0.30** across
runs, the pipeline flags `POSSIBLE_LOOKAHEAD` — at that level it is almost
certainly a bug, not skill.

## Signal A — 8-K sentiment method

Tone = (n_positive − n_negative) / (n_positive + n_negative), computed over the
cleaned primary-document text of each 8-K, using the **Loughran-McDonald (LM)**
finance sentiment word lists — the standard public lexicon for financial text.

- If `data/lm_master_dictionary.csv` (the full public LM dictionary) is present,
  it is used by default.
- Otherwise a small, clearly-labeled **baseline** word list is used so the
  pipeline runs end-to-end. The baseline is a transparent placeholder, **not**
  a proprietary list. For research-grade results, drop in the full LM
  dictionary CSV. See `code/sentiment.py`.

Only relevant text is stored (capped at 200k chars/filing) so the repository
stays well under GitHub's per-file (100 MB) and repo size limits.

## Signal B — Google Trends factor

Weekly search interest per company name, fetched via `pytrends` (throttled,
batched). Feature = week-over-week change, lagged so only closed weeks are used.
Google Trends rescales history and is revision-prone, so it is treated as a
coarse feature and documented as such.

## Survivorship bias (known limitation)

One-time setup expands the universe toward **today's** S&P 500 membership
(public Wikipedia list). This introduces **survivorship bias**: companies
removed or delisted during the lookback window are absent, which can inflate
apparent signal quality. We approximate the universe with current membership
and **document the bias rather than hide it**. A point-in-time constituent
history would be required to remove it fully; that is noted as future work.

Other limitations: prices come from Yahoo Finance (`yfinance`) and are
split/dividend adjusted (`auto_adjust=True`). Adjusted prices embed later
corporate actions, a subtle lookahead; over the 1-5 day forward horizons used
here the effect is negligible and does not change the sign of returns, and this
is disclosed rather than hidden. Google Trends values are relative and
re-scaled over time; the baseline sentiment lexicon is intentionally simple
until the full LM dictionary is supplied.

## Run state & resumability

`code/run_pipeline.py` detects state from `results/run_log.csv`:
- **First run** (log has only a header) → one-time setup (expand universe,
  backfill ~6 months of 8-Ks and ~2 years of prices, initial Trends, baseline
  signals + IC).
- **Otherwise** → incremental update since the last successful run.

Every stage is wrapped in try/except with retries + exponential backoff for
external requests; failures are logged to `run_log.csv`
(`run_time,stage,status,count,error_summary`) and partials are saved so the
project is always resumable. If a source blocks us, partial results are kept
and the next run resumes.

## Self-checks (end of every run)

- If a stage failed ≥2× in the last 5 log rows → surfaced as a ⚠️ warning.
- If `|IC|` > 0.30 in recent `ic_history.csv` rows → `POSSIBLE_LOOKAHEAD`.
- Coverage drops / missing-data spikes are visible via per-ticker log rows.

## No fabricated numbers

Every figure traces to a real file under `data/`, `signals/`, or `results/`.
Missing data is recorded as "insufficient data" and skipped — never estimated.
