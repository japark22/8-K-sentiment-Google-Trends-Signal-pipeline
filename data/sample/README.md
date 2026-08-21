# Sample data (format examples)

These are a few small example files showing the exact format the pipeline
produces. The full datasets (all S&P 500 tickers) are **not** committed to keep
the repository lightweight — they are regenerable at any time by running the
pipeline (`python code/run_pipeline.py`), which writes to `data/prices/`,
`data/filings_8k/`, and `data/trends/`.

- `prices_AAPL_example.csv` — daily OHLC prices (date, open, high, low, close, volume)
- `filings_8k_AAPL_example.csv` — 8-K metadata incl. EDGAR `accepted_datetime`
- `trends_example.csv` — weekly Google Trends interest (week, interest)
