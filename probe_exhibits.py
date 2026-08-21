#!/usr/bin/env python3
"""Probe: are we scoring the 8-K cover page instead of the press release?

Two questions, both answerable in about twenty throttled requests:

  1. Does EDGAR's submissions JSON carry the 8-K `items` field we are not
     storing? (2.02 = results of operations, 5.02 = officer changes,
     1.01 = material agreement. Pooling those together dilutes any signal.)

  2. How much text lives in the EX-99 exhibits we never download? The
     earnings release is the exhibit; the primary document is usually a
     one-page cover.

Writes nothing. Run from the repository root with .env loaded:

    set -a; source .env; set +a
    python3 probe_exhibits.py
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, "code")
import config  # noqa: E402

TICKERS = ["AAPL", "JPM", "XOM"]
PER_TICKER = 3
SLEEP = 0.5

INDEX_JSON = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/index.json"
DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"

EX99_NAME = re.compile(r"ex[-_]?99", re.I)
TEXTUAL = re.compile(r"\.(htm|html|txt)$", re.I)


def strip_html(html: str) -> str:
    t = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;|&#160;", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z']+", text))


def get(session, url):
    time.sleep(SLEEP)
    r = session.get(url, headers={"User-Agent": config.SEC_USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r


def load_ciks() -> dict:
    out = {}
    p = config.UNIVERSE_CSV
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["ticker"]] = r.get("cik", "")
    return out


def main() -> None:
    if "(" in config.SEC_USER_AGENT and "()" in config.SEC_USER_AGENT:
        sys.exit("SEC_CONTACT_EMAIL is empty. Run: set -a; source .env; set +a")
    print(f"User-Agent: {config.SEC_USER_AGENT}\n")

    ciks = load_ciks()
    session = requests.Session()

    total_primary = total_exhibit = 0
    items_seen, exhibit_names = [], []

    for tk in TICKERS:
        cik = ciks.get(tk, "")
        if not cik:
            print(f"{tk}: no CIK in universe.csv, skipping")
            continue
        try:
            data = get(session, config.SEC_SUBMISSIONS_URL.format(cik10=cik)).json()
        except Exception as exc:
            print(f"{tk}: submissions failed: {exc}")
            continue

        recent = data.get("filings", {}).get("recent", {})
        has_items = "items" in recent
        print(f"=== {tk} (CIK {cik})   submissions has 'items' field: {has_items}")
        if not has_items:
            print(f"    available keys: {sorted(recent.keys())}")

        idx = [i for i, f in enumerate(recent.get("form", [])) if f == "8-K"][:PER_TICKER]
        cik_int = int(cik)

        for i in idx:
            acc = recent["accessionNumber"][i]
            acc_nodash = acc.replace("-", "")
            primary = recent["primaryDocument"][i]
            items = (recent.get("items") or [""] * (i + 1))[i] if has_items else ""
            items_seen.append(items)

            try:
                pw = words(strip_html(get(session, DOC_URL.format(
                    cik_int=cik_int, acc_nodash=acc_nodash, doc=primary)).text))
            except Exception as exc:
                print(f"    {acc}: primary fetch failed: {exc}")
                continue

            try:
                listing = get(session, INDEX_JSON.format(
                    cik_int=cik_int, acc_nodash=acc_nodash)).json()
                entries = listing.get("directory", {}).get("item", [])
            except Exception as exc:
                print(f"    {acc}: index.json failed: {exc}")
                entries = []

            cands = []
            for e in entries:
                name = e.get("name", "")
                etype = str(e.get("type", "") or "")
                if name == primary or not TEXTUAL.search(name):
                    continue
                if EX99_NAME.search(name) or etype.upper().startswith("EX-99"):
                    cands.append((name, etype, int(e.get("size") or 0)))

            ew = 0
            for name, etype, size in cands:
                exhibit_names.append(f"{name} (type={etype or 'n/a'})")
                try:
                    ew += words(strip_html(get(session, DOC_URL.format(
                        cik_int=cik_int, acc_nodash=acc_nodash, doc=name)).text))
                except Exception as exc:
                    print(f"    {acc}: exhibit {name} failed: {exc}")

            total_primary += pw
            total_exhibit += ew
            print(f"    {acc}  items={items or 'n/a':<12} "
                  f"primary={pw:>6,}w   EX-99={ew:>7,}w  "
                  f"({len(cands)} exhibit file(s))")
        print()

    print("-" * 68)
    print(f"primary-document words total : {total_primary:>8,}")
    print(f"EX-99 exhibit words total    : {total_exhibit:>8,}")
    if total_primary:
        print(f"text we are currently missing: {total_exhibit / total_primary:>8.1f}x "
              f"the text we score")
    print(f"\nitems values seen: {sorted(set(x for x in items_seen if x))}")
    print("exhibit filenames matched:")
    for n in sorted(set(exhibit_names)):
        print("   ", n)
    if not exhibit_names:
        print("    NONE - the filename/type heuristic missed. Paste the output")
        print("    so the matcher can be corrected before the full refetch.")


if __name__ == "__main__":
    main()
