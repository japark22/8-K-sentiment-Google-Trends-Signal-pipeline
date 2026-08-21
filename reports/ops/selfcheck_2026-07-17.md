# Daily Self-Check — 2026-07-17 (Fri)

Status: **⚠️ PROBLEMS FOUND** — pipeline has not run successfully in ~11 days.

## What was checked
- results/run_log.csv (last rows, run_start/run_end pairing, status counts)
- results/ic_history.csv (lookahead flags, |IC| threshold)
- results/pipeline.log and results/launchd.err.log
- data coverage counts (prices / filings_8k / trends)

## Findings

### 1. ⚠️ Scheduled pipeline failing daily — "Operation not permitted" (PRIMARY)
`results/launchd.err.log` (last modified **2026-07-16 18:00**) contains 9 identical errors:
```
/bin/bash: .../code/run_auto.sh: Operation not permitted
```
The launchd job is firing on schedule but macOS is denying execution of `run_auto.sh`. This has blocked every scheduled run since Jul 6. Most likely cause: Full Disk Access / TCC permission not granted to the launchd agent (or the script's exec bit / quarantine attribute on the real disk), so the scheduled job cannot launch the pipeline.

### 2. ⚠️ No successful full run since 2026-07-06 (11 days)
Last `run_log.csv` row is `2026-07-06T08:13:47Z, run_start, INCREMENTAL UPDATE` with **no matching `run_end`** — the Jul 6 incremental run died mid-way (during the trends stage). No `run_end` within the last ~2 days → pipeline has effectively stopped.

### 3. Google Trends rate-limiting (429) on the last real run
185 of the last 200 run_log rows are `fetch_trends_ticker, failed, ... code 429`. Trends stage was throttled/blocked by Google on Jul 6. Known limitation; contributed to the run dying without run_end.

### 4. git push FAILED on Jul 6
`pipeline.log` ends with `fatal: No configured push destination` → `push FAILED (check GitHub credentials)`. Remote not configured / credentials missing at scheduled pipeline time, so results were not pushed.

### 5. Data coverage (informational)
prices: 502 dirs · filings_8k: 304 dirs · trends: 46 csv files. Trends coverage low, consistent with the 429 failures. No prior-run baseline to compare a sharp drop against.

## Self-check gates
- IC lookahead: ic_history.csv has 3 rows (8k_sentiment, h=1/3/5), |IC| ≤ 0.021, **no POSSIBLE_LOOKAHEAD flag**. Healthy.
- Repeated-failure gate: `fetch_trends_ticker` failed repeatedly (429) and scheduled pipeline `run_auto.sh` fails every day → flagged above.

## Bottom line
The pipeline is stalled. Scheduled pipeline cannot execute (`Operation not permitted`) and the last manual/auto run never completed. Needs a manual kick + fixing launchd permission and git push credentials.
