"""
Build / expand the investable universe and resolve SEC CIK numbers.

- Seed universe lives in data/universe.csv (ticker, company).
- One-time setup expands it toward the S&P 500 using a PUBLIC source
  (Wikipedia's List of S&P 500 companies).
- CIK numbers are resolved from SEC's official public mapping file
  (company_tickers.json) so no identifier is ever fabricated.

SURVIVORSHIP BIAS NOTE: expanding to *today's* index membership introduces
survivorship bias (delisted / removed names are absent). We document this
limitation rather than silently ignore it; see PIPELINE_NOTES.md.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import requests

import config
import utils

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def load_universe() -> list[dict]:
    if not config.UNIVERSE_CSV.exists():
        return []
    with open(config.UNIVERSE_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _norm_ticker(t: str) -> str:
    # SEC uses '-' style tickers (e.g. BRK-B). Normalize dots to dashes.
    return t.strip().upper().replace(".", "-")


def resolve_ciks(session: requests.Session, rows: list[dict]) -> list[dict]:
    """Attach a zero-padded 10-digit 'cik' to each row using SEC's mapping.
    Rows whose ticker is not found are kept but marked cik='' (insufficient)."""
    resp = utils.get_with_retry(
        session, config.SEC_TICKERS_URL,
        headers={"User-Agent": config.SEC_USER_AGENT}, key="sec",
    )
    mapping = {}
    for item in resp.json().values():
        mapping[_norm_ticker(item["ticker"])] = str(item["cik_str"]).zfill(10)

    out = []
    for r in rows:
        tk = _norm_ticker(r.get("ticker", ""))
        cik = mapping.get(tk, "")
        out.append({"ticker": tk, "company": r.get("company", ""), "cik": cik})
    return out


def expand_to_sp500(session: requests.Session, existing: list[dict]) -> list[dict]:
    """Add S&P 500 constituents from Wikipedia to the existing seed list.
    Falls back to the seed list untouched if the source is unavailable."""
    have = {_norm_ticker(r["ticker"]) for r in existing}
    try:
        import pandas as pd  # local import; optional dependency
        resp = utils.get_with_retry(
            session, SP500_WIKI_URL,
            headers={"User-Agent": config.SEC_USER_AGENT},
            key="wiki", min_interval=1.0,
        )
        tables = pd.read_html(io.StringIO(resp.text))
        df = tables[0]
        for _, row in df.iterrows():
            tk = _norm_ticker(str(row.get("Symbol", "")))
            name = str(row.get("Security", "")).strip()
            if tk and tk not in have:
                existing.append({"ticker": tk, "company": name})
                have.add(tk)
    except Exception as exc:  # noqa: BLE001
        utils.log_run("build_universe", "partial", len(existing),
                      f"S&P500 expand failed, kept seed only: {exc}")
    return existing


def write_universe(rows: list[dict]) -> None:
    config.UNIVERSE_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["ticker", "company", "cik"]
    with open(config.UNIVERSE_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def run(session: requests.Session, expand: bool = False) -> list[dict]:
    """Load seed, optionally expand to S&P 500, resolve CIKs, persist.
    Returns the resolved universe (list of dicts with ticker/company/cik)."""
    rows = load_universe()
    if not rows:
        raise RuntimeError("universe.csv is empty or missing seed tickers")
    if expand:
        rows = expand_to_sp500(session, rows)
    resolved = resolve_ciks(session, rows)
    write_universe(resolved)
    n_with_cik = sum(1 for r in resolved if r["cik"])
    utils.log_run("build_universe", "success", n_with_cik,
                  f"{len(resolved)} names, {n_with_cik} CIKs resolved")
    return resolved
