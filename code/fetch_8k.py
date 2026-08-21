"""
Fetch 8-K filing metadata and body text from SEC EDGAR.

The critical field is `acceptanceDateTime` -- the EDGAR ACCEPTED timestamp.
This is the first moment the filing became public and is what point-in-time
forward returns are anchored to (NOT filingDate alone).

WHAT CHANGED, AND WHY
---------------------
1) WE WERE SCORING THE COVER PAGE. The previous version downloaded only
   `primaryDocument` -- for most 8-Ks a one-page cover of legal boilerplate.
   The news is in the exhibits: measured on four real filings, the earnings
   release is 3x to 13x the text of the cover it is attached to. Median words
   per filing was 669 and only 0.71% of them were sentiment words, well under
   the 1.5-3% normal for financial prose. We were measuring boilerplate.

2) EXHIBIT FILENAMES CANNOT BE GUESSED. Exxon files its release as
   `livef8k2q26991.htm` and JPMorgan as `a2q26_earningsxpresentat.htm` --
   neither contains "ex99". The `type` field in EDGAR's index.json is also
   not the document type: it reported an earnings-release HTML file as
   "text.gif". Both heuristics were tested and both fail.

   The authoritative source is the complete submission text file. It is SGML,
   and every document inside carries a <TYPE> header set by the filer. We keep
   TYPE 8-K and TYPE EX-99* and drop everything else -- which also excludes
   the XBRL viewer artifacts (R1.htm, MetaLinks.json) that would otherwise
   add a couple of thousand junk words to every single filing.

3) BANDWIDTH. A complete submission runs 0.3-3 MB because graphics and XBRL
   are inlined. Document order is always 8-K, then EX-99*, then the
   EX-101/GRAPHIC/ZIP block that EDGAR appends. So we stream and hang up as
   soon as a stop marker appears. That keeps one request per filing -- fewer
   than fetching an index plus each document separately -- without pulling
   megabytes of base64 images we would throw away.

4) ITEM NUMBERS. The submissions JSON carries `items` (e.g. "2.02,9.01") and
   we were discarding it. Item 2.02 is results of operations, 5.02 an officer
   change, 1.01 a material agreement. Pooling them means a good earnings
   release and a resignation land in the same bucket. Now stored per filing.

Output: data/filings_8k/<TICKER>.csv, one row per 8-K, columns:
  ticker, cik, accession, form, filing_date, accepted_datetime, items,
  primary_doc, doc_url
Plus data/filings_8k/text/<accession>.txt -- the 8-K body and its EX-99
exhibits, concatenated and stripped of markup.

Existing text files were written by the old cover-page-only code. Delete the
text directory once before the first run so they are refetched:

    rm -rf data/filings_8k/text
"""
from __future__ import annotations

import csv
import re
import datetime as dt
import time

import requests

import config
import utils

ARCHIVE_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"
SUBMISSION_TXT_URL = ("https://www.sec.gov/Archives/edgar/data/"
                      "{cik_int}/{acc_nodash}/{acc}.txt")
TEXT_DIR = config.FILINGS_DIR / "text"

MAX_TEXT_CHARS = 400_000      # cap stored text per filing
MAX_FETCH_BYTES = 20 * 1024 * 1024   # hard stop if the stop marker never shows

# Document types worth scoring. EX-99 with no suffix is used by some filers
# (JPMorgan's earnings presentation), so match the prefix, not "EX-99.1".
KEEP_EXACT = {"8-K", "8-K/A"}
KEEP_PREFIX = "EX-99"

# Everything after the first of these is EDGAR-appended machinery: XBRL
# taxonomy files, inlined images, the xbrl zip. Never contains news.
STOP_MARKERS = (b"<TYPE>EX-101", b"<TYPE>GRAPHIC", b"<TYPE>ZIP",
                b"<TYPE>EX-100", b"<TYPE>XML", b"<TYPE>JSON")

DOC_RE = re.compile(r"<DOCUMENT>(.*?)(?:</DOCUMENT>|\Z)", re.S)
TYPE_RE = re.compile(r"<TYPE>([^\r\n<]+)")
TEXT_RE = re.compile(r"<TEXT>(.*?)(?:</TEXT>|\Z)", re.S)


def _strip_html(html: str) -> str:
    txt = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
    txt = re.sub(r"&nbsp;|&#160;", " ", txt)
    txt = re.sub(r"&amp;", "&", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _wanted(dtype: str) -> bool:
    d = dtype.strip().upper()
    return d in KEEP_EXACT or d.startswith(KEEP_PREFIX)


def _is_binary_payload(body: str) -> bool:
    head = body[:2000]
    return "<PDF>" in head or "begin 644" in head


def _fetch_submission(session: requests.Session, url: str) -> tuple[str, int, bool]:
    """Stream the complete submission, stopping at the first XBRL/graphic
    marker. Returns (text, bytes_read, stopped_early)."""
    utils.throttle(key="sec")
    with session.get(url, headers={"User-Agent": config.SEC_USER_AGENT},
                     timeout=config.REQUEST_TIMEOUT_SEC, stream=True) as resp:
        if resp.status_code in (429, 503):
            raise RuntimeError(f"rate-limited HTTP {resp.status_code}")
        resp.raise_for_status()
        buf = bytearray()
        for chunk in resp.iter_content(chunk_size=131_072):
            if not chunk:
                continue
            buf += chunk
            cut = min((p for p in (buf.find(m) for m in STOP_MARKERS) if p != -1),
                      default=-1)
            if cut != -1:
                return bytes(buf[:cut]).decode("utf-8", "ignore"), len(buf), True
            if len(buf) >= MAX_FETCH_BYTES:
                return bytes(buf).decode("utf-8", "ignore"), len(buf), True
        return bytes(buf).decode("utf-8", "ignore"), len(buf), False


def extract_text(raw: str) -> tuple[str, list[str]]:
    """Return (concatenated text, list of TYPE values kept)."""
    parts, kept = [], []
    for block in DOC_RE.findall(raw):
        tm = TYPE_RE.search(block)
        if not tm or not _wanted(tm.group(1)):
            continue
        bm = TEXT_RE.search(block)
        if not bm:
            continue
        body = bm.group(1)
        if _is_binary_payload(body):
            continue
        cleaned = _strip_html(body)
        if cleaned:
            parts.append(cleaned)
            kept.append(tm.group(1).strip())
    return (" ".join(parts)[:MAX_TEXT_CHARS], kept)


def fetch_ticker_8ks(session: requests.Session, ticker: str, cik: str,
                     since: dt.date, fetch_text: bool = True) -> list[dict]:
    """Return 8-K rows for one company filed on/after `since`.
    Raises on hard request failure; returns [] if none found."""
    if not cik:
        raise RuntimeError("insufficient data (no CIK for ticker)")
    url = config.SEC_SUBMISSIONS_URL.format(cik10=cik)
    resp = utils.get_with_retry(
        session, url, headers={"User-Agent": config.SEC_USER_AGENT}, key="sec",
    )
    data = resp.json()
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accepted = recent.get("acceptanceDateTime", [])
    accnos = recent.get("accessionNumber", [])
    primary = recent.get("primaryDocument", [])
    items_col = recent.get("items", [])
    cik_int = int(cik)

    rows = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        try:
            fdate = dt.date.fromisoformat(dates[i])
        except Exception:
            continue
        if fdate < since:
            continue
        acc = accnos[i]
        acc_nodash = acc.replace("-", "")
        doc = primary[i] if i < len(primary) else ""
        doc_url = ""
        if doc:
            doc_url = ARCHIVE_DOC_URL.format(cik_int=cik_int, acc_nodash=acc_nodash,
                                             doc=doc)
        rows.append({
            "ticker": ticker,
            "cik": cik,
            "accession": acc,
            "form": form,
            "filing_date": dates[i],
            # EDGAR accepted timestamp (Eastern). The anchor for point-in-time.
            "accepted_datetime": accepted[i] if i < len(accepted) else "",
            # e.g. "2.02,9.01". Empty for older filings that predate the field.
            "items": items_col[i] if i < len(items_col) else "",
            "primary_doc": doc,
            "doc_url": doc_url,
        })

        # Only download text we do not already have, so incremental runs are
        # fast and gentle on SEC (respect-sources rule).
        text_path = TEXT_DIR / f"{acc_nodash}.txt"
        if fetch_text and not text_path.exists():
            sub_url = SUBMISSION_TXT_URL.format(cik_int=cik_int,
                                                acc_nodash=acc_nodash, acc=acc)
            try:
                raw, nbytes, _ = _fetch_submission(session, sub_url)
                text, kept = extract_text(raw)
                if not text:
                    raise RuntimeError(
                        f"no scorable document found in {nbytes:,}B submission")
                TEXT_DIR.mkdir(parents=True, exist_ok=True)
                tmp = text_path.with_suffix(".tmp")
                tmp.write_text(text, encoding="utf-8")
                tmp.replace(text_path)          # atomic: no half-written file
                if any(k.upper().startswith(KEEP_PREFIX) for k in kept):
                    _STATS["with_exhibit"] += 1
                _STATS["bytes"] += nbytes
            except Exception as exc:  # noqa: BLE001
                utils.log_run("fetch_8k_text", "failed", 0, f"{ticker} {acc}: {exc}")
                time.sleep(0.5)
    return rows


_STATS = {"with_exhibit": 0, "bytes": 0}


def run(session: requests.Session, universe: list[dict],
        fetch_text: bool = True) -> int:
    """Fetch 8-Ks for the whole universe over the lookback window.
    Writes one CSV per ticker. Returns total filings captured."""
    _STATS["with_exhibit"] = 0
    _STATS["bytes"] = 0
    since = dt.date.today() - dt.timedelta(days=config.FILINGS_LOOKBACK_DAYS)
    total, failures = 0, 0
    for row in universe:
        tk, cik = row["ticker"], row.get("cik", "")
        try:
            rows = fetch_ticker_8ks(session, tk, cik, since, fetch_text=fetch_text)
            if rows:
                out = config.FILINGS_DIR / f"{tk}.csv"
                with open(out, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    w.writeheader()
                    w.writerows(rows)
                total += len(rows)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            utils.log_run("fetch_8k_ticker", "failed", 0, f"{tk}: {exc}")

    status = "success" if failures == 0 else ("partial" if total else "failed")
    note = (f"{total} 8-Ks since {since.isoformat()}, {failures} tickers failed")
    if fetch_text:
        note += (f"; {_STATS['with_exhibit']} with EX-99 text, "
                 f"{_STATS['bytes']/1024/1024:.0f}MB fetched")
    utils.log_run("fetch_8k", status, total, note)
    print(f"  fetch_8k: {note}")
    return total
