# Ops Self-Check — 2026-07-14 (Tue)

Scheduled weekday health check. Local files only; no external data fetched.

## Verdict: ⚠️ PROBLEM (actionable, escalating) — scheduled pipeline still broken; pipeline has now not run for 8 days

Sixth flagged weekday (07-07, 07-08, 07-09, 07-10, 07-13, 07-14; weekends not scheduled). The launchd job last fired **2026-07-13 18:13** and failed again with `Operation not permitted`, so still no new pipeline run. The stall that crossed the 2-day threshold on 07-08 is now at 8 calendar days. Root cause is unchanged and still unaddressed.

## What was checked

### 1. results/run_log.csv — ⚠️ pipeline stalled (8 days)
- Last `run_start`: **2026-07-06T08:13:47Z** (INCREMENTAL UPDATE). No new run 07-07 through 07-14.
- Last complete `run_end`: **2026-07-06T07:52:07Z**. → 8 days with no successful full run; staleness threshold far exceeded.
- Starts vs ends: **5 starts / 2 ends** — the last incremental attempt (07-06) never reached `run_end`; it stopped after `build_universe` (503 names).
- The ~24 rows before it are all `fetch_trends_ticker` `failed` with HTTP **429** (Google Trends rate limit) — a secondary, pre-existing issue, unchanged.

### 2. results/launchd.err.log — ⚠️ root cause, recurred again
- Modified **2026-07-13 18:13**; now contains **six** identical lines:
  `code/run_auto.sh: Operation not permitted`
- launchd fired on 07-07, 07-08, 07-09, 07-10, and 07-13 and could **not execute** `run_auto.sh`. The script carries the execute bit, so this is a macOS TCC / Full Disk Access block on running a script inside the protected Desktop location — not a missing chmod.

### 3. results/ic_history.csv — ✅ healthy (but stale)
- 8k_sentiment IC: h1 = -0.0018, h3 = 0.0206, h5 = 0.0091 (n ≈ 1945–1994).
- All |IC| well below 0.30. No POSSIBLE_LOOKAHEAD flag. Values unchanged since 07-06 because no new run has produced fresh IC.

### 4. results/pipeline.log — stale (unchanged since 07-06)
- Last entry `2026-07-06 16:13:59 scheduled pipeline done`. One historical `push FAILED` from the 07-06 setup run; not a current issue.
- No new scheduled pipeline output since 07-06 confirms the launchd job has not successfully run for 8 days.

### 5. Coverage — no data loss
- prices: **502** | filings_8k: **304** | trends: **46**. Unchanged from prior checks. Trends still capped at the 46-ticker seed by the 429 limit. No sharp coverage drop.

## Most likely fix
1. **Un-stick now (manual run)** — in Terminal:
   `cd "<project>" && source .venv/bin/activate && python code/run_pipeline.py`
2. **Fix scheduled pipeline root cause:** grant **Full Disk Access** to the process launchd uses (`/bin/bash` and/or the launchd agent) in System Settings → Privacy & Security → Full Disk Access, since the script lives under the TCC-protected Desktop folder. Then confirm the next scheduled fire writes a fresh `run_end`.

Trends 429 remains a secondary, non-urgent issue (increase backoff / run trends-only later).

## Alert sent
Short Korean message recorded in the run log (problem is actionable, recurring, now at 8 days / 6th flagged weekday).
