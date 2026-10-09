#!/usr/bin/env python3
"""Probe 2: read document types from the complete submission file.

Probe 1 showed that guessing exhibit filenames fails and that index.json's
`type` field is not the EDGAR document type (it reported an earnings release
HTML file as "text.gif"). EDGAR does publish the authoritative type: the
complete submission text file is SGML, and every document inside it carries a
<TYPE> header. One request per filing returns the cover page AND every
exhibit, so this is also fewer requests than the current approach.

The open question is size -- graphics and PDFs are base64-inlined -- so this
measures it on the exact filings probe 1 failed on before anything is
committed to a full refetch.

Writes nothing. Run from the repository root with .env loaded:

    set -a; source .env; set +a
    python3 probe_sgml.py
"""
from __future__ import annotations

import re
import sys
import time

import requests

sys.path.insert(0, "code")
import config  # noqa: E402

# (ticker, cik, accession) -- taken from probe 1. The JPM and XOM rows are the
# ones where the filename heuristic found nothing.
CASES = [
    ("AAPL", "0000320193", "0000320193-26-000018"),   # 2.02,9.01 - matched before
    ("JPM",  "0000019617", "0001193125-26-314128"),   # 8.01,9.01 - missed before
    ("JPM",  "0000019617", "0001628280-26-048086"),   # 7.01,9.01 - missed before
    ("XOM",  "0002115436", "0002115436-26-000006"),   # 2.02,7.01 - missed before
]

SUBMISSION_TXT = ("https://www.sec.gov/Archives/edgar/data/"
                  "{cik_int}/{acc_nodash}/{acc}.txt")
MAX_BYTES = 15 * 1024 * 1024
SLEEP = 0.5

DOC_RE = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.S)
TYPE_RE = re.compile(r"<TYPE>([^\r\n<]+)")
FILENAME_RE = re.compile(r"<FILENAME>([^\r\n<]*)")
DESC_RE = re.compile(r"<DESCRIPTION>([^\r\n<]*)")
TEXT_RE = re.compile(r"<TEXT>(.*?)</TEXT>", re.S)


def strip_html(html: str) -> str:
    t = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;|&#160;", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z']+", text))


def fetch_capped(session, url: str) -> tuple[str, int, bool]:
    """Return (text, bytes_read, truncated). Streams so a huge PDF exhibit
    cannot blow up memory."""
    time.sleep(SLEEP)
    with session.get(url, headers={"User-Agent": config.SEC_USER_AGENT},
                     timeout=60, stream=True) as r:
        r.raise_for_status()
        buf, size = [], 0
        for chunk in r.iter_content(chunk_size=262_144):
            if not chunk:
                continue
            buf.append(chunk)
            size += len(chunk)
            if size >= MAX_BYTES:
                return (b"".join(buf).decode("utf-8", "ignore"), size, True)
        return (b"".join(buf).decode("utf-8", "ignore"), size, False)


def main() -> None:
    if "()" in config.SEC_USER_AGENT:
        sys.exit("SEC_CONTACT_EMAIL is empty. Run: set -a; source .env; set +a")
    print(f"User-Agent: {config.SEC_USER_AGENT}\n")

    session = requests.Session()
    all_types = set()

    for tk, cik, acc in CASES:
        url = SUBMISSION_TXT.format(cik_int=int(cik), acc_nodash=acc.replace("-", ""),
                                    acc=acc)
        try:
            raw, size, truncated = fetch_capped(session, url)
        except Exception as exc:
            print(f"{tk} {acc}: FAILED {exc}\n")
            continue

        docs = DOC_RE.findall(raw)
        print(f"=== {tk} {acc}")
        print(f"    submission {size/1024/1024:.2f} MB, {len(docs)} document(s)"
              + ("  [TRUNCATED at cap]" if truncated else ""))
        if not docs:
            print("    no <DOCUMENT> blocks found -- format assumption is WRONG")
            print(f"    first 300 chars: {raw[:300]!r}\n")
            continue

        for d in docs:
            tm = TYPE_RE.search(d)
            dtype = tm.group(1).strip() if tm else "?"
            all_types.add(dtype)
            fn = FILENAME_RE.search(d)
            fname = fn.group(1).strip() if fn else ""
            dm = DESC_RE.search(d)
            desc = (dm.group(1).strip()[:40] if dm else "")
            body = TEXT_RE.search(d)
            btxt = body.group(1) if body else ""
            is_bin = "<PDF>" in btxt[:2000] or "begin 644" in btxt[:2000]
            w = 0 if is_bin else words(strip_html(btxt))
            print(f"    TYPE={dtype:<12} {w:>7,}w  {'BINARY ' if is_bin else '       '}"
                  f"{fname:<34} {desc}")
        print()

    print("-" * 74)
    print("distinct TYPE values seen:", sorted(all_types))
    keep = sorted(t for t in all_types
                  if t.upper().startswith("EX-99") or t.upper() == "8-K")
    print("would be kept for scoring (8-K + EX-99.*):", keep)


if __name__ == "__main__":
    main()
