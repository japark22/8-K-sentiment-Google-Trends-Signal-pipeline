"""
Signal A: 8-K filing sentiment.

Method (transparent, public, reproducible):
- Tone = (n_positive - n_negative) / (n_positive + n_negative) using the
  Loughran-McDonald (LM) finance sentiment word lists, the standard PUBLIC
  lexicon for financial text.
- If the full LM master dictionary CSV is present at
  data/lm_master_dictionary.csv it is used; otherwise a small, clearly
  labeled BASELINE word list is used so the pipeline runs end-to-end. The
  baseline is a placeholder, NOT a proprietary list; swap in the full LM
  dictionary for research-grade results (see PIPELINE_NOTES.md).

Output: signals/sentiment.csv with columns:
  ticker, accession, accepted_datetime, filing_date, tone, n_pos, n_neg, n_words
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import config
import utils

LM_CSV = config.DATA_DIR / "lm_master_dictionary.csv"
FILINGS_TEXT_DIR = config.FILINGS_DIR / "text"

# Baseline placeholder lexicon (documented; replace with full LM dictionary).
_BASELINE_POS = {
    "gain", "gains", "growth", "profit", "profits", "improved", "improvement",
    "strong", "stronger", "record", "increase", "increased", "success",
    "successful", "positive", "beneficial", "favorable", "opportunity",
    "opportunities", "achieved", "outperform", "upgrade", "expansion",
}
_BASELINE_NEG = {
    "loss", "losses", "decline", "declined", "decrease", "decreased", "weak",
    "weaker", "negative", "adverse", "litigation", "lawsuit", "impairment",
    "default", "restructuring", "downgrade", "investigation", "breach",
    "termination", "resign", "resigned", "delay", "shortfall", "deficiency",
}

_WORD_RE = re.compile(r"[A-Za-z']+")


def load_lexicon() -> tuple[set[str], set[str], bool]:
    """Return (positive, negative, used_full_lm)."""
    if LM_CSV.exists():
        pos, neg = set(), set()
        with open(LM_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                word = (r.get("Word") or "").strip().lower()
                if not word:
                    continue
                if (r.get("Positive") or "0") not in ("0", "", None):
                    pos.add(word)
                if (r.get("Negative") or "0") not in ("0", "", None):
                    neg.add(word)
        if pos and neg:
            return pos, neg, True
    return _BASELINE_POS, _BASELINE_NEG, False


def score_text(text: str, pos: set[str], neg: set[str]) -> tuple[float, int, int, int]:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    n_pos = sum(1 for w in words if w in pos)
    n_neg = sum(1 for w in words if w in neg)
    denom = n_pos + n_neg
    tone = (n_pos - n_neg) / denom if denom else 0.0
    return tone, n_pos, n_neg, len(words)


def run() -> int:
    """Score every 8-K we have text for. Returns rows written."""
    pos, neg, used_full = load_lexicon()
    if not used_full:
        utils.log_run("sentiment", "partial", 0,
                      "using BASELINE lexicon (full LM dictionary not found)")

    out_rows = []
    for csv_path in sorted(config.FILINGS_DIR.glob("*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                acc_nodash = r["accession"].replace("-", "")
                tpath = FILINGS_TEXT_DIR / f"{acc_nodash}.txt"
                if not tpath.exists():
                    continue  # insufficient data -> skip, never invent a score
                text = tpath.read_text(encoding="utf-8", errors="ignore")
                tone, np_, nn_, nw = score_text(text, pos, neg)
                out_rows.append({
                    "ticker": r["ticker"],
                    "accession": r["accession"],
                    "accepted_datetime": r.get("accepted_datetime", ""),
                    "filing_date": r.get("filing_date", ""),
                    "tone": round(tone, 6),
                    "n_pos": np_, "n_neg": nn_, "n_words": nw,
                })

    config.SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.SIGNALS_DIR / "sentiment.csv"
    fields = ["ticker", "accession", "accepted_datetime", "filing_date",
              "tone", "n_pos", "n_neg", "n_words"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    utils.log_run("sentiment", "success", len(out_rows),
                  f"{len(out_rows)} filings scored (full_LM={used_full})")
    return len(out_rows)
