# Point-in-time S&P 500 with the verified rename map (HYPOTHESES.md H1)

**H1a passes, narrowly.** On the renamed-map PIT universe, momentum v2's
bull/bear interaction against the PIT equal-weight benchmark is
**+0.075% a day, 95% CI [+0.003%, +0.152%]**. Momentum does relatively
worse in bear markets than in bull markets. That is the opposite of the
published "drawdown protection", and it confirms, as a pre-registered
test, the direction first seen exploratorily on `results/pit_us`
(+0.081% [+0.009, +0.156]). The lower bound is very close to zero, so this
is a weak confirmation.

**H1b (descriptive).** 20 mappings were accepted (`../pit_us/RENAME_MAP.md`).
Member-day coverage rose from **74.3% to 76.7%**. Results barely moved.

## Coverage (`coverage.json`)

| | Before (`pit_us`) | After (renamed) |
|---|---|---|
| Member-days covered, 2005–2024 | 74.3% | **76.7%** |
| 2005 | 53.3% | 55.5% |
| 2010 | 64.8% | 67.4% |
| 2015 | 73.5% | 76.3% |
| 2024 | 95.7% | 95.8% |

The gain is spread over the whole period: renamed names were members for
years under their old tickers. Most of the remaining 23% of member-days
belong to names that were acquired or went bankrupt, and those need
delisted prices, which free data doesn't have.

## Results (`comparison.csv`), 2009-01-05 to 2024-12-30, engine v2

| | Momentum CAGR | Sharpe | Max DD | Benchmark CAGR | Sharpe | Max DD | Interaction (bull − bear, /day) | 95% CI |
|---|---|---|---|---|---|---|---|---|
| Fixed 37 names | 27.2% | 1.06 | −35.9% | 29.7% | 1.19 | −45.9% | −0.015% | [−0.131, +0.081] |
| PIT, before rename map | 13.7% | 0.71 | −36.1% | 14.0% | 0.81 | −36.1% | +0.081% | [+0.009, +0.156] |
| **PIT, renamed (H1)** | **14.0%** | **0.72** | **−35.3%** | **14.0%** | **0.81** | **−36.1%** | **+0.075%** | **[+0.003, +0.152]** |
| PIT liquid-40, renamed | 22.5% | 0.88 | −38.6% | 14.0% | 0.81 | −36.1% | +0.156% | [+0.039, +0.271] |

## Reading it

- **The rename map is a small correction.** It adds about 2.4 points of
  coverage and moves CAGR by 0.3 points or less. The survivorship gap
  against the fixed list (about 13–16 CAGR points) is not an artefact of
  missing renames.
- **The sign flip is stable.** With better coverage, momentum still does
  worse relative to the benchmark in bear markets, and the effect is
  significant. Point estimate and CI barely change.
- **Remaining bias.** The 23% of member-days still missing are mostly
  failures and cash takeovers. Momentum tends to *avoid* names on their
  way to failure, because they are losers before they delist. So the
  missing names probably depress the benchmark more than momentum, and
  the true momentum-minus-benchmark gap is probably a little *more*
  favourable to momentum than shown. That is a reasoned guess, not
  something this data can show.

## Files

`run_pit_renamed.py`, `coverage.json`, `h1_result.json`, `comparison.csv`,
`curves/`, and `rename_candidates.csv` (every candidate with every check).
