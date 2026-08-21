# 8-K sentiment: what was tested, and what the sample can and cannot say

Sample: 3,553 8-K filings from 503 S&P 500 constituents, accepted between
2026-02-19 and 2026-08-21. 125 distinct entry dates.

## Conclusion in one line

Loughran-McDonald tone measured on 8-K text shows no detectable relationship
with short-horizon forward returns in this sample. That is **not** evidence
that no relationship exists: the sample can only resolve |IC| above roughly
0.045 overall and 0.111 for earnings filings, while the effect sizes reported
in the literature for standalone tone are 0.01-0.03. The test was
underpowered by a factor of two to four before it was run.

## Headline numbers

Cross-sectional rank IC of tone against market-adjusted forward returns,
averaged within entry date and tested across dates (see "Why by-date" below).

| group | window | IC | t | dates |
|---|---|---|---|---|
| all 8-K | close -> +1d | +0.0138 | +0.64 | 124 |
| all 8-K | close -> +3d | +0.0167 | +0.73 | 122 |
| all 8-K | close -> +5d | +0.0018 | +0.08 | 120 |
| item 2.02 | session (open->close, day 1) | +0.0013 | +0.03 | 46 |
| item 2.02 | close -> +1d | +0.0601 | +1.06 | 46 |
| item 5.07 (placebo) | session | +0.0895 | +1.32 | 25 |

Eighteen tests were run across six item groups and three horizons, so the
Bonferroni threshold is |t| > 2.99. Nothing came within half of it.

## What was ruled out, and how

Each of these was a way for a null result to be an artefact rather than a
finding. Each was closed before the conclusion was written.

**The statistic was wrong.** Pooling all filings and using SE = 1/sqrt(n-1)
treats clustered observations as independent. On this sample the pooled
estimator reported IC +0.0373 with t = +2.19 at the 5-day horizon while the
by-date estimator on the same data gave t = +0.50. The pooled number would
have been reported as a finding. Every figure above is by-date.

**The return was mostly the market.** Filings cluster in earnings season, so
a batch of them shares one market move that has nothing to do with tone.
Every return is now excess of an equal-weighted benchmark built from the same
503 tickers over the same window. Note that subtracting a per-date constant
does not change a within-date rank correlation, so this correction matters
only to the pooled estimator -- which is a further reason to read the by-date
column.

**The lexicon was a toy.** The tone measure was running on a 24-word
placeholder list, not the LM dictionary (354 positive / 2,355 negative).
Swapping it in changed the 3-day pooled IC from -0.0144 to +0.0221 and
stabilised the sign. Any conclusion drawn before that swap was meaningless.

**We were scoring the wrong text.** Only `primaryDocument` was downloaded --
for most 8-Ks a one-page legal cover. Median words per filing was 669 with
0.71% sentiment-word density, well under the 1.5-3% normal for financial
prose. The news is in the EX-99 exhibits.

Exhibit filenames cannot be guessed: Exxon files its release as
`livef8k2q26991.htm`, JPMorgan as `a2q26_earningsxpresentat.htm`. EDGAR's
`index.json` `type` field is also not the document type -- it reported an
earnings-release HTML file as `text.gif`. Both heuristics were tested and
both failed. The authoritative source is the complete submission text file,
whose SGML carries a filer-set `<TYPE>` per document.

After switching to it: 1,990 of 3,553 filings carry EX-99 text, median words
rose 669 -> 1,924, density 0.71% -> 1.61%, zero degenerate texts. On four
hand-checked filings the release is 3x to 13x the cover it is attached to.

Adding that text did **not** improve prediction. The all-8-K 3-day by-date
t moved from +1.21 to +0.73. This is recorded as-is.

**8-K is a container, not an event.** Item 2.02 is results of operations,
5.02 an officer change, 1.01 a material agreement. A positive earnings
release and a warmly-worded resignation pull opposite ways and cancel.
Filings are now split by item, with hypotheses fixed in advance: 2.02
expected to carry signal, 7.01 and 8.01 expected null, 5.02 and 1.01 marked
exploratory. Splitting did not produce a result either.

**The measurement window was in the wrong place.** Entry was the close of the
first bar strictly after acceptance -- a correct lookahead guard, but stricter
than necessary. An 8-K accepted at 20:23 ET is public before the next day's
open, so that open is tradable, and entering at the following close discards
an entire session.

This was tested by decomposing the return into the overnight gap, the day-1
session, open-to-h and close-to-h, each market-adjusted the same way. On
synthetic data with an effect planted only in the day-1 session, the session
window reports t = +8.1 while the close-to-close rule reports t = -0.9 --
confirming the rule is blind to that case. On the real data, item 2.02 gives
gap t = -0.39 and session t = +0.03. The signal is not hiding in the discarded
window; it is not there.

**A placebo behaves like the treatment.** Item 5.07 reports the tally of a
shareholder vote: procedural, outcome known before filing, no business
content. Its session IC is +0.0895, larger in magnitude than item 2.02's
+0.0013. When the control group produces bigger numbers than the hypothesis
group, the honest reading is that every number in the table is noise-scale.

## Why by-date rather than pooled

A pooled Spearman across all filings assumes independent observations. 8-Ks
arrive in clusters and filings sharing an entry date share a return shock, so
the pooled standard error is too small and its t too large. The by-date
estimator computes a cross-sectional IC within each date with at least five
filings, then tests the mean of that series across dates. Each date
contributes one observation and the common shock cancels. Where the two
disagree, the by-date figure is the one reported.

## What would settle it

Power, not another slice of the same data. Observed by-date standard errors
imply:

- all 8-K, to resolve IC = 0.02: 613 entry dates (have 122)
- item 2.02, to resolve IC = 0.05: 227 earnings dates (have 46)

Both land near two and a half years of filings.

| | current | required |
|---|---|---|
| `FILINGS_LOOKBACK_DAYS` | 183 | 950 |
| `PRICES_LOOKBACK_DAYS` | 730 | 1,150 |
| filings | 3,553 | ~18,500 |
| collection time | 38 min | ~3.3 h |

One caveat on that extension: `filings.recent` in the EDGAR submissions JSON
holds a bounded number of recent filings per company, with older ones in the
`filings.files` shards. Two and a half years is well inside `recent` for a
typical filer, but a very frequent filer could be silently truncated, and
that should be checked rather than assumed.

Further slicing of the present sample is not worth doing. Eighteen tests have
already been spent on it; more would buy false positives, not information.

## Beyond more history

If a 2.5-year sample still shows nothing, the likely reason is the measure
rather than the horizon. The published result is that tone matters
*conditional on the earnings surprise*; unconditional tone is close to
uninformative because every release is written positively and the
cross-sectional spread in tone is largely writing style and industry
vocabulary. Testing the conditional version needs an expectations series,
which is not available from a free source. A free approximation is
year-over-year fundamentals from the XBRL company-facts endpoint, which is a
fundamental change rather than a surprise against expectations -- weaker, but
honest about what it is.

## Reproducing

`probe_exhibits.py` and `probe_sgml.py` at the repository root are the two
throwaway scripts that established why filename matching was abandoned in
favour of the SGML document types. They are kept as the record of that
decision.
