# Ops Self-Check — 2026-07-08 (Wed)

Scheduled weekday health check. Local files only; no external data fetched.

## Verdict: ⚠️ PROBLEM (actionable) — scheduled scheduled pipeline is failing; pipeline has not run for 2 days

This escalates yesterday's read. On 2026-07-07 the launchd error was judged "benign." It is not: the scheduler tried to run and failed, and the pipeline has produced no new run since 2026-07-06.

## What was checked

### 1. results/run_log.csv — ⚠️ pipeline stalled
- Last `run_start`: **2026-07-06T08:13:47Z** (INCREMENTAL UPDATE). No new run on 07-07 or 07-08.
- Last complete `run_end`: **2026-07-06T07:52:07Z**. → No successful full run within the last ~2 days; the 2-day staleness threshold is now crossed.
- Last 20 rows: 18 `failed`, all `fetch_trends_ticker` HTTP **429** (Google Trends rate limit) — same trends throttling seen 07-07.

### 2. results/launchd.err.log — ⚠️ NEW, this is the root cause
- Modified **2026-07-07 18:00**; contains two identical lines:
  `code/run_auto.sh: Operation not permitted`
- The launchd job fired on 07-07 at 18:00 and could **not execute** `run_auto.sh`, so no pipeline run happened. `run_auto.sh` has the execute bit set (`-rwx------`), so this is a macOS permission (TCC / Full Disk Access) block on running a script inside the protected Desktop location — not a missing chmod.

### 3. results/ic_history.csv — ✅ healthy
- 8k_sentiment IC: h1 = -0.0018, h3 = 0.0206, h5 = 0.0091 (n ≈ 1945–1994).
- All |IC| well below 0.30. No POSSIBLE_LOOKAHEAD flag.

### 4. results/pipeline.log — benign / stale
- One `push FAILED` ("No configured push destination") dating from the 07-06 setup run. Remote `origin` is now configured; not a current issue.

### 5. Coverage — no data loss
- prices: 502 | filings_8k: 304 | trends: 46. Unchanged from 07-07. Trends still capped at the 46-ticker seed by the 429 limit.

## Most likely fix
Two things, in order:
1. **Un-stick now (manual run):** in Terminal —
   `cd "<project>" && source .venv/bin/activate && python code/run_pipeline.py`
2. **Fix scheduled pipeline root cause:** grant **Full Disk Access** to the process launchd uses (`/bin/bash` and/or the launchd agent) in System Settings → Privacy & Security → Full Disk Access, since the script lives under the TCC-protected Desktop folder. Re-arm the launchd job and confirm the next scheduled fire writes a fresh `run_end`.

Trends 429 remains a secondary, non-urgent issue (increase backoff / run trends-only later).
