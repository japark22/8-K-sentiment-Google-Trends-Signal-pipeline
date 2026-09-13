# APAC Phase 1 — Korea (DART) Disclosure-Sentiment Signal

Public data only. Deployed on Tencent Cloud (Hong Kong).
Data: 259,541 KRX (KOSPI+KOSDAQ) disclosures over 2 years (2024-09 to 2026-09);
daily prices for 2,594 tickers via KRX (pykrx).

Signal v1: keyword-lexicon tone over each disclosure title (report_nm).
Point-in-time: forward returns from the first trading day strictly AFTER the
filing's receipt date. Evaluation: Spearman rank IC; market-adjusted (returns
demeaned cross-sectionally per receipt date); long-short (positive vs negative
tone); and first-year / second-year stability.

Results (n ~ 43,000 scored disclosures):

| Horizon | raw IC | mkt-adj IC | L/S (pos-neg) | stability Y1/Y2 |
|--------:|-------:|-----------:|--------------:|-----------------|
| 1d | 0.014 | 0.017 | +0.06% | 0.005 / 0.026 |
| 2d | 0.026 | 0.031 | +0.08% | 0.022 / 0.038 |
| 3d | 0.028 | 0.032 | +0.05% | 0.030 / 0.034 |
| 5d | 0.033 | 0.034 | +0.09% | 0.021 / 0.044 |

Read: a small but consistent positive signal that survives market-adjustment,
strengthens with horizon (consistent with under-reaction), and is positive in
both years. Modest effect size is expected for title-only sentiment.

Limitations / next: title-only lexicon (upgrade to full-text KR-FinBERT);
market- but not yet sector-neutral; overlapping return windows (significance);
no transaction-cost/turnover accounting in the L/S. Hong Kong market next.
