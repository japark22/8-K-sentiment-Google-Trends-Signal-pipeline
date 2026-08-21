# Ops Self-Check — 2026-08-14 (Fri)

Scheduled weekday health check. Local files only; no external data fetched.

## Verdict: ⚠️ PROBLEM (recurring, unchanged) — scheduled pipeline still broken; pipeline has now not completed a run for 39 days

Same root cause as every flagged check since early July, still unaddressed. No new failure mode, no data loss, no deterioration. Stable-but-stalled. One new launchd fire since the last check (Thu 08-13 evening), which failed identically.

## What was checked
- results/run_log.csv (last rows, run_start/run_end pairing, latest timestamp)
- results/ic_history.csv (lookahead flags, |IC| threshold)
- results/launchd.err.log and results/pipeline.log
- data coverage counts (prices / filings_8k / trends)

## Findings

### 1. ⚠️ Scheduled pipeline failing on every scheduled fire — "Operation not permitted" (PRIMARY, unchanged)
`results/launchd.err.log`, last modified **2026-08-13 18:00**, now holds **29** identical lines:
```
/bin/bash: .../code/run_auto.sh: Operation not permitted
```
One more than the 08-13 check (28 → 29), consistent with a single launchd fire on Thu 08-13 evening. Zero non-matching lines — no new error type. launchd keeps firing on the weekday schedule but macOS denies execution of `run_auto.sh`. Cause unchanged: the script lives under the TCC-protected Desktop folder and the process launchd uses lacks Full Disk Access — a permission block, not a missing execute bit (`run_auto.sh` is `-rwx------`, execute bit present).

### 2. ⚠️ No successful full run since 2026-07-06 (39 days)
Last complete `run_end`: **2026-07-06T07:52:07Z** ("INCREMENTAL UPDATE (--only ic,sentiment,trends_factor)"). The final Jul 6 incremental `run_start` (08:13:47Z) never reached a matching `run_end` — it died during the trends stage. No `run_end` within the last ~2 days → pipeline effectively stopped. `run_log.csv` unchanged since 2026-07-06 (mtime 07-06 16:13); latest row timestamp is 2026-07-06T08:13:48Z. Only 2 `run_end` rows total in the log.

### 3. Google Trends 429 rate-limiting on the last real run (secondary, pre-existing)
The last ~20 real run_log rows before the stall are `fetch_trends_ticker, failed` with HTTP **429**. Trends was throttled by Google on Jul 6 and contributed to that run dying without `run_end`. Known limitation; not the scheduled pipeline blocker.

### 4. results/ic_history.csv — ✅ healthy (but stale)
3 rows, all 8k_sentiment: h1 = -0.0018, h3 = 0.0206, h5 = 0.0091 (n ≈ 1945–1994). All |IC| well below 0.30. **No POSSIBLE_LOOKAHEAD flag.** Values unchanged since 07-06 (no new run has produced fresh IC).

### 5. results/pipeline.log — stale, no new content
Last entry `2026-07-06 16:13:59 scheduled pipeline done`, which also records a `push FAILED` ("No configured push destination"). No new activity; consistent with the pipeline not having run. A git remote IS now configured (`origin → github.com/japark22/8-K-sentiment-Google-Trends-Signal-pipeline.git`), so that Jul 6 push error predates the remote setup and is not a current active blocker; it will only re-verify once scheduled pipeline runs again.

### 6. Coverage — no data loss
prices: **502** CSVs | filings_8k: **304** entries | trends: **46** CSVs. Unchanged from prior checks. Trends still capped at the 46-ticker seed by the 429 limit. No sharp coverage drop.

## Self-check gates
- IC lookahead gate: |IC| ≤ 0.021, no flag → healthy.
- Repeated-failure gate: `run_auto.sh` fails on every fire; `fetch_trends_ticker` failed repeatedly (429) → flagged above (⚠️ at top).

## Most likely fix
1. **Un-stick now (manual run)** — in Terminal:
   `cd "<project>" && source .venv/bin/activate && python code/run_pipeline.py`
2. **Fix scheduled pipeline root cause:** grant **Full Disk Access** to the process launchd uses (`/bin/bash` and/or the launchd agent) in System Settings → Privacy & Security → Full Disk Access, since `run_auto.sh` sits under the protected Desktop folder. Confirm the next scheduled fire writes a fresh `run_end`.

Trends 429 remains a secondary, non-urgent issue (increase backoff / run trends-only later).

## Alert
Problem is recurring and still unaddressed at 39 days — short, calm Korean status message recorded in the run log. Kept brief since it repeats a known, unchanged issue.
