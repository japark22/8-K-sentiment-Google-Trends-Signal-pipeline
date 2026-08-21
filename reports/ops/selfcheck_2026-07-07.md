# Ops Self-Check — 2026-07-07 (Tue)

Scheduled weekday health check. Local files only; no external data fetched.

## Verdict: ⚠️ ONE PROBLEM (non-urgent) — Google Trends fully rate-limited

## What was checked

### 1. results/run_log.csv — ⚠️ repeated stage failure
- Last activity: 2026-07-06 (Mon), within the 2-day window → pipeline is running.
- Last 40 rows: 11 success, 1 partial, **28 failed** — every failure is `fetch_trends_ticker` returning HTTP **429** (Google Trends rate limit).
- `fetch_trends_ticker,success` count across entire log: **0**. No trends ticker has ever been fetched successfully by the pipeline.
- Other stages healthy: `run_start`, `build_universe` (503 names / 503 CIKs), prices, sentiment, IC all `success`.
- Note: the final `run_start` (INCREMENTAL UPDATE, 08:13:47Z) has no matching `run_end` row, but pipeline.log shows the wrapper completed at 16:13:59 HKT — the git commit stage ran, so the run finished; the missing run_end is cosmetic.

### 2. results/ic_history.csv — ✅ healthy
- 8k_sentiment IC: h1 = -0.0018, h3 = 0.0206, h5 = 0.0091 (n ≈ 1945–1994).
- All |IC| well below 0.30. No POSSIBLE_LOOKAHEAD flag. No lookahead concern.

### 3. results/pipeline.log & launchd.err.log — ✅ resolved / benign
- pipeline.log contains one `push FAILED` ("No configured push destination") from the setup run.
- **Now resolved**: git remote `origin` is configured (github.com/japark22/8-K-sentiment-Google-Trends-Signal-pipeline) and `main` is in sync with `origin/main` (both at 1a099bd). Nothing to push; no current git problem.
- launchd.err.log: `run_auto.sh: Operation not permitted` — permissions/launchd note, not affecting the last successful run.

### 4. Coverage — ✅ no sharp drop
- prices: 502 files | filings_8k: 304 files | trends: 46 files.
- Trends coverage (46 / 503 universe) is low but expected: it is the setup seed; expansion is blocked purely by the 429 rate limit, not by data loss. First real check, so no prior-run baseline to diff against.

## Most likely fix (for the one problem)
Google Trends is throttling the pipeline (429). Not a credentials issue and not urgent — it is expected to clear with more backoff. Increase the inter-request delay / exponential backoff in the trends stage and re-run trends-only later in the day, or accept the 46-ticker seed for now. Pipeline is resumable; no data was lost.
