# Ops Self-Check — 2026-07-30 (Thu)

Scheduled weekday health check. Local files only; no external data fetched.

## Verdict: ⚠️ PROBLEM (recurring, unchanged) — scheduled pipeline still broken; pipeline has now not run for 24 days

Root cause is unchanged from every prior flagged check and still unaddressed. No new failure mode and no data loss. Stable-but-stalled, not deteriorating.

Note: no self-check ran on Tue 07-28 or Wed 07-29 (no report files for those days), so this is the first monitor pass since Mon 07-27. The scheduled pipeline kept firing and failing on both missed days (see below).

## What was checked
- results/run_log.csv (last rows, run_start/run_end pairing, status tally)
- results/ic_history.csv (lookahead flags, |IC| threshold)
- results/launchd.err.log and results/pipeline.log
- data coverage counts (prices / filings_8k / trends)

## Findings

### 1. ⚠️ Scheduled pipeline failing on every scheduled fire — "Operation not permitted" (PRIMARY, unchanged)
`results/launchd.err.log`, last modified **2026-07-29 18:06**, now holds **18** identical lines:
```
/bin/bash: .../code/run_auto.sh: Operation not permitted
```
Three more than the 07-27 check (15 → 18), consistent with one launchd fire each on Mon 07-27, Tue 07-28, and Wed 07-29 evening. launchd keeps firing on the weekday schedule but macOS denies execution of `run_auto.sh`. Most likely cause unchanged: the script lives under the TCC-protected Desktop folder and the process launchd uses (`/bin/bash` / the launchd agent) lacks Full Disk Access — a permission block, not a missing execute bit (`run_auto.sh` still carries owner-execute).

### 2. ⚠️ No successful full run since 2026-07-06 (24 days)
Last complete `run_end`: **2026-07-06T07:52:07Z**. Overall run_start=5 vs run_end=2; the final Jul 6 incremental `run_start` (08:13:47Z) never reached a matching `run_end` — it died during the trends stage. No `run_end` within the last ~2 days → pipeline effectively stopped. `run_log.csv` unchanged since 2026-07-06.

### 3. Google Trends 429 rate-limiting on the last real run (secondary, pre-existing)
Of the last 20 run_log rows, 18 are `fetch_trends_ticker, failed` with HTTP **429**. Trends stage was throttled by Google on Jul 6 and contributed to that run dying without `run_end`. Known limitation; not the scheduled pipeline blocker.

### 4. results/ic_history.csv — ✅ healthy (but stale)
3 rows, all 8k_sentiment: h1 = -0.0018, h3 = 0.0206, h5 = 0.0091 (n ≈ 1945–1994). All |IC| well below 0.30. **No POSSIBLE_LOOKAHEAD flag.** Values unchanged since 07-06 (no new run has produced fresh IC).

### 5. results/pipeline.log — stale, no new content
Last entry `2026-07-06 16:13:59 scheduled pipeline done`. No new activity; consistent with the pipeline not having run.

### 6. Coverage — no data loss
prices: **502** CSVs | filings_8k: **303** CSVs (+2004 text files) | trends: **46** CSVs. Unchanged from prior checks. (An apparent jump this pass was a file-counting artifact from including the `filings_8k/text/` subdirectory; per-ticker CSV coverage is identical.) Trends still capped at the 46-ticker seed by the 429 limit. No sharp coverage drop.

## Self-check gates
- IC lookahead gate: |IC| ≤ 0.021, no flag → healthy.
- Repeated-failure gate: `run_auto.sh` fails on every fire and `fetch_trends_ticker` failed repeatedly (429) → flagged above (⚠️ at top).

## Most likely fix
1. **Un-stick now (manual run)** — in Terminal:
   `cd "<project>" && source .venv/bin/activate && python code/run_pipeline.py`
2. **Fix scheduled pipeline root cause:** grant **Full Disk Access** to the process launchd uses (`/bin/bash` and/or the launchd agent) in System Settings → Privacy & Security → Full Disk Access, since `run_auto.sh` sits under the protected Desktop folder. Confirm the next scheduled fire writes a fresh `run_end`.

Trends 429 remains a secondary, non-urgent issue (increase backoff / run trends-only later).

## Alert
Problem is recurring and still unaddressed at 24 days — short Korean status message recorded in the run log, kept brief and calm since it repeats a known, unchanged issue.
