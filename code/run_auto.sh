#!/bin/bash
# Scheduled pipeline run for the 8-K Sentiment + Google Trends project.
# Activates the venv, runs the incremental pipeline, then commits & pushes to
# GitHub. Launched on a schedule by macOS launchd (hands-off).
#
# RELIABLE ALERTS: on any failure this posts a native macOS notification
# (works even when the Cowork app is closed, because launchd runs on the Mac).
# All progress is appended to results/pipeline.log.

set -uo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$PROJECT/results/pipeline.log"

# Local, gitignored settings (SEC_CONTACT_EMAIL and anything else the run
# needs). launchd does not read your shell profile, so they must be loaded
# here rather than exported in a terminal.
if [ -f "$PROJECT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT/.env"
  set +a
fi

# Post a macOS notification (banner + sound). Safe no-op if osascript missing.
notify() {
  local msg="$1"
  /usr/bin/osascript -e "display notification \"${msg}\" with title \"8-K + Trends Pipeline\" sound name \"Basso\"" 2>/dev/null || true
}

cd "$PROJECT" || { echo "cannot cd to project"; exit 1; }
echo "===== $(date '+%Y-%m-%d %H:%M:%S') scheduled pipeline start =====" >> "$LOG"

# Activate the virtual environment.
if [ -f "$PROJECT/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$PROJECT/.venv/bin/activate"
else
  echo "ERROR: .venv not found; recreate it (see README)" >> "$LOG"
  notify "Scheduled pipeline failed: Python .venv is missing. Recreate it (see README)."
  exit 1
fi

# Run the pipeline. No flags = auto-detect (incremental after first run).
python code/run_pipeline.py >> "$LOG" 2>&1
PY_EXIT=$?

# Detect critical STAGE failures in this run (stage summary rows only, not the
# expected per-ticker Google-Trends 429 noise).
STAGE_FAILS=$(tail -60 "$LOG" >/dev/null 2>&1; \
  tail -60 results/run_log.csv 2>/dev/null \
  | grep -E ',(fetch_prices|fetch_8k|sentiment|compute_ic),failed,' \
  | wc -l | tr -d ' ')

if [ "$PY_EXIT" -ne 0 ] || [ "${STAGE_FAILS:-0}" -gt 0 ]; then
  echo "PIPELINE PROBLEM (exit=$PY_EXIT, stage_fails=$STAGE_FAILS)" >> "$LOG"
  notify "Pipeline run had a problem. Open Terminal and check results/pipeline.log."
fi

# Commit and push any new data / results / reports.
# Clear a stale git lock first (a crashed/interrupted git leaves index.lock,
# which would silently block every future commit).
if [ -f .git/index.lock ]; then
  echo "clearing stale .git/index.lock" >> "$LOG"
  rm -f .git/index.lock
fi

if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  if git add -A >> "$LOG" 2>&1 \
     && git commit -m "Scheduled pipeline run $(date '+%Y-%m-%d %H:%M')" >> "$LOG" 2>&1; then
    if git push >> "$LOG" 2>&1; then
      echo "push OK" >> "$LOG"
    else
      echo "push FAILED" >> "$LOG"
      notify "GitHub push failed — your access token may have expired. Re-auth needed."
    fi
  else
    echo "COMMIT FAILED" >> "$LOG"
    notify "Git commit failed (see results/pipeline.log). Data updated locally but not pushed to GitHub."
  fi
else
  echo "no changes to commit" >> "$LOG"
fi

echo "===== $(date '+%Y-%m-%d %H:%M:%S') scheduled pipeline done =====" >> "$LOG"
