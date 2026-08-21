"""
Central configuration for the 8-K Sentiment + Google Trends signal pipeline.

ABSOLUTE RULES (see PIPELINE_NOTES.md):
- Public data only: SEC EDGAR, public price data, Google Trends.
- Point-in-time discipline: a signal at time T uses only info public at T.
- No fabricated numbers. Missing data -> "insufficient data", never invented.
- Respect sources: proper User-Agent, throttling, retries, backoff.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Paths -----------------------------------------------------------------
# The project root is the parent of this code/ directory.
ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
PRICES_DIR = DATA_DIR / "prices"
FILINGS_DIR = DATA_DIR / "filings_8k"
TRENDS_DIR = DATA_DIR / "trends"
SIGNALS_DIR = ROOT / "signals"
RESULTS_DIR = ROOT / "results"
REPORTS_DIR = ROOT / "reports"

UNIVERSE_CSV = DATA_DIR / "universe.csv"
RUN_LOG_CSV = RESULTS_DIR / "run_log.csv"
IC_HISTORY_CSV = RESULTS_DIR / "ic_history.csv"

# --- SEC EDGAR -------------------------------------------------------------
# SEC requires a descriptive User-Agent with a contact address. It is read
# from the environment and is deliberately NOT stored in this file:
#     export SEC_CONTACT_EMAIL="you@example.com"
# With it unset the User-Agent still identifies the project, but setting it
# is what SEC fair-access guidance asks for.
SEC_CONTACT_EMAIL = os.environ.get("SEC_CONTACT_EMAIL", "")
SEC_USER_AGENT = f"8K-Trends-Research/1.0 ({SEC_CONTACT_EMAIL})"

# SEC fair-access guidance is <=10 requests/second. We stay well under that.
SEC_MIN_INTERVAL_SEC = 0.4  # ~2.5 req/s, conservative
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"

# --- Backfill windows ------------------------------------------------------
FILINGS_LOOKBACK_DAYS = 183   # ~6 months of 8-K filings
PRICES_LOOKBACK_DAYS = 730    # ~2 years of daily prices
TRENDS_LOOKBACK = "today 12-m"  # Google Trends relative window

# --- Signal / evaluation parameters ---------------------------------------
# Forward-return horizons (trading days) measured from the FIRST tradable
# moment AFTER the filing's EDGAR accepted_datetime.
FORWARD_HORIZONS = [1, 3, 5]
PRIMARY_HORIZON = 5

# Sanity guard: |IC| persistently above this almost certainly means a bug
# (lookahead), not skill. Flagged in reports and ic_history.
IC_LOOKAHEAD_THRESHOLD = 0.30

# --- Requests --------------------------------------------------------------
MAX_RETRIES = 3
BACKOFF_BASE_SEC = 2.0  # exponential: 2, 4, 8 ...
REQUEST_TIMEOUT_SEC = 30
