# Ops Self-Check — 2026-07-09 (Thu)

Scheduled weekday health check. Local files only; no external data fetched.

## Verdict: ⚠️ PROBLEM (actionable, escalating) — scheduled pipeline still broken; pipeline has now not run for 3 days

Third consecutive day flagged. The launchd job fired again on **2026-07-08 18:14** and again failed with `Operation not permitted`, so no new pipeline run occurred. The stall that crossed the 2-day threshold on 07-08 is now at 3 days.

## What was checked

### 1. results/run_log.csv — ⚠️ pipeline stalled (3 days)
- Last `run_start`: **2026-07-06T08:13:47Z** (INCREMENTAL UPDATE). No new run on 07-07, 07-08, or 07-09.
- Last complete `run_end`: **2026-07-06T07:52:07Z**. → 3 days with no successful full run; staleness threshold well exceeded.
- run_start / run_end count: 5 starts vs 2 ends — the last incremental attempt never reached run_end.
- Last ~24 rows: all `fetch_trends_ticker` `failed` with HTTP **429** (Google Trends rate limit), unchanged from prior days.

### 2. results/launchd.err.log — ⚠️ root cause, recurred again
- Modified **2026-07-08 18:14**; now contains three identical lines:
  `code/run_auto.sh: Operation not permitted`
- launchd fired on 07-07 and 07-08 and could **not execute** `run_auto.sh`. The script has the execute bit (`-rwx------`), so this is a macOS TCC / Full Disk Access block on running a script inside the protected Desktop location — not a missing chmod.

### 3. results/ic_history.csv — ✅ healthy
- 8k_sentiment IC: h1 = -0.0018, h3 = 0.0206, h5 = 0.0091 (n ≈ 1945–1994).
- All |IC| well below 0.30. No POSSIBLE_LOOKAHEAD flag.

### 4. results/pipeline.log — stale (unchanged since 07-06)
- Last entry `2026-07-06 16:13:59 scheduled pipeline done`. One historical `push FAILED` from the 07-06 setup run; remote is now configured, not a current issue.
- No new scheduled pipeline output since 07-06 confirms the launchd job has not successfully run.

### 5. Coverage — no data loss
- prices: 502 | filings_8k: 304 | trends: 46. Unchanged from 07-07/07-08. Trends still capped at the 46-ticker seed by the 429 limit.

## Most likely fix
1. **Un-stick now (manual run)** — in Terminal:
   `cd "<project>" && source .venv/bin/activate && python code/run_pipeline.py`
2. **Fix scheduled pipeline root cause:** grant **Full Disk Access** to the process launchd uses (`/bin/bash` and/or the launchd agent) in System Settings → Privacy & Security → Full Disk Access, since the script lives under the TCC-protected Desktop folder. Then confirm the next scheduled fire writes a fresh `run_end`.

Trends 429 remains a secondary, non-urgent issue (increase backoff / run trends-only later).

## Alert sent
Short Korean message recorded in the run log (problem is actionable and recurring).
