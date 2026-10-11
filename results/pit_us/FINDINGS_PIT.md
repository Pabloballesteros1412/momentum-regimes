# Survivorship bias, US: momentum v2 on a point-in-time S&P 500

**Short answer.** The fixed 37-name list inflates returns a lot. Over
2009–2024 out of sample, equal-weight buy & hold falls from **29.7% CAGR
on the fixed list to 14.0% on the point-in-time S&P 500**, and momentum
v2 falls from **27.2% to 13.7%**. Momentum's shortfall against its
benchmark shrinks from −2.5 to −0.3 points a year. The regime result
changes sign: on the point-in-time universe, momentum's gap to the
benchmark is significantly *worse* in bear markets than in bull markets.
That is the opposite of "drawdown protection", and the same direction as
Europe. Coverage is incomplete: **351 of 943 historical members (37%)
have no free price data**, and the missing names are mostly ones that
failed or were acquired. These numbers are still biased upward, just less
than the fixed list.

## Data

- **Membership:** [fja05680/sp500](https://github.com/fja05680/sp500),
  daily S&P 500 member lists, at commit `a2430f2`. They are reduced to
  per-ticker membership intervals on SPY's trading calendar
  (`data/sp500_membership_intervals.csv`; source and date in
  `data/sp500_membership_SOURCE.txt`). 943 distinct tickers were members
  at some point in 2005–2024, for 2,519,921 member-days.
- **Prices:** Yahoo Finance only. Stooq is blocked from this environment,
  and Tiingo needs an API key. `cache/` is gitignored, so the prices are
  not committed; `build_universe_us.py` re-downloads them.

### Coverage (`coverage_summary.csv`, `coverage_by_year.csv`, `coverage_by_ticker.csv`)

| | Names | |
|---|---|---|
| Price found for every member-day | 575 | |
| Found for part of the membership | 12 | e.g. DOW, FOXA, CEG, DELL: Yahoo has only the post-spin-off/re-IPO company |
| **Missing entirely** | **351** | 334 left the index before 2024; 17 were still members at the end of 2024 but have since been acquired or renamed (ANSS, JNPR, HES, DFS, WBA, …), so Yahoo no longer has them |
| Excluded as reused tickers | 5 | CPWR, GENZ, KG, SII, SUN: Yahoo's series starts after the original company joined and keeps trading years after it left, so the symbol now belongs to a different company |

**Member-day coverage is 74.3% overall.** It rises from 53% in 2005 to
96% in 2024. That is the survivorship gradient itself: the further back,
the more of the index has since disappeared.

Ticker reuse that leaves Yahoo's dates looking plausible can't be detected
without a second source. Two checks were applied (a late start, and a late
start plus leaving the index) and are reported per ticker.

## Engine pieces (opt-in, default path unchanged)

- `quantbt/data/universe.py` `UniverseSchedule`: is `symbol` a member on
  `date`?
- `quantbt/strategies/pit.py`:
  - `PointInTimeMomentum`: ranks only current members. A held name that
    leaves the index exits at the next rebalance.
  - `PointInTimeEqualWeight` + `PITEqualWeightSizer`: the benchmark.
    Equal weight across current members with a price, rebalanced monthly.
    `BuyAndHold` would accumulate every name that ever joined.
  - The PIT sizers liquidate a held name on the last bar of its data, at
    its close × (1 + delisting return). Without this, the position would
    be frozen and unsellable.
  - `PointInTimeLiquidMomentum`: a breadth control that ranks only the 40
    most liquid current members, by 63-day dollar volume.
- `test_universe.py`:
  - An always-member schedule reproduces the fixed-universe run exactly.
  - No buy is signalled on a non-member day.
  - A name whose data ends is liquidated, with or without a haircut.
  - The liquid variant with no cap equals the fixed run.

**Not run: the −30% delisting-return sensitivity (Shumway 1997).** It is
implemented, but it can't trigger on this data. All 622 Yahoo series run
to the end of 2024, because Yahoo keeps only still-listed symbols, so no
held name's data ever ends early. That is the clearest sign of what's
missing: the names that would need a delisting return aren't in the
sample at all.

## Results (`comparison.csv`)

Common out-of-sample window: 2009-01-05 to 2024-12-30, 4,024 days, engine
v2, the same 12-combination grid and 16 folds as the regime study.

| Universe | Momentum CAGR | Sharpe | Max DD | Benchmark CAGR | Sharpe | Max DD |
|---|---|---|---|---|---|---|
| Fixed 37 names (`results/v2`) | 27.2% | 1.06 | −35.9% | 29.7% (B&H) | 1.19 | −45.9% |
| PIT S&P 500 (~500 names) | **13.7%** | 0.71 | −36.1% | **14.0%** (PIT EW) | 0.81 | −36.1% |
| PIT, 40 most liquid members | 23.3% | 0.90 | −38.6% | 14.0% (PIT EW, all members) | 0.81 | −36.1% |

The 40-most-liquid row is not like-for-like: its benchmark is the
equal-weight S&P 500, not an equal weight of the same 40 names. It shows
that a narrow, large-cap, point-in-time universe still earns a lot more
than the broad one. The fixed list's extra return comes from survivorship
*and* from concentrating on today's mega-caps.

### Regime interaction (momentum − benchmark, bullish minus bearish, mean daily)

| Universe | Bullish gap | Bearish gap | Interaction | 95% CI | |
|---|---|---|---|---|---|
| Fixed 37 names | −0.009% | +0.006% | −0.015% | [−0.131, +0.081] | n.s. |
| PIT S&P 500 | +0.016% | −0.065% | **+0.081%** | [+0.009, +0.156] | **sig.** |
| PIT, 40 most liquid | +0.066% | −0.084% | **+0.149%** | [+0.028, +0.266] | **sig.** |

On a point-in-time universe, momentum keeps up with or beats the
benchmark in bull markets and lags it in bear markets. That is the
textbook momentum-crash pattern (Daniel and Moskowitz 2016), and the
opposite of the drawdown-protection claim. Europe shows the same sign
(`results/v2`).

These two tests were not in a pre-registered family and were run after
the main v2 result was known. Treat them as exploratory. With 74%
coverage, and the missing names concentrated among failures, the true
point-in-time interaction can't be pinned down from this data. What the
data does show is that the fixed-list null is not robust to the universe,
and the direction it moves in is against protection.

## How much the results move

| | Fixed → PIT S&P 500 |
|---|---|
| Momentum CAGR | 27.2% → 13.7% (−13.5 pp) |
| Benchmark CAGR | 29.7% → 14.0% (−15.7 pp) |
| Momentum − benchmark CAGR | −2.5 pp → −0.3 pp |
| Momentum Sharpe | 1.06 → 0.71 |
| Bull − bear interaction | −0.015% (n.s.) → +0.081% (sig., opposite sign to the published claim) |
| Momentum invested fraction | 0.986 → 0.977 |
| Holdings at a rebalance | ~4–8 → ~40–100 (10–20% of the members with prices) |

## What would improve this

1. **A rename map.** Many "missing" names are renames that Yahoo now lists
   under a new ticker, for example ANTM→ELV, PKI→RVTY, BLL→BALL, ABC→COR,
   MYL→VTRS, SYMC→GEN, GPS→GAP, CTL→LUMN, LB→BBWI, STI→TFC. A verified
   `data/ticker_map.csv` could recover a large share of member-days.
   Each mapping needs a spot-check for splices, which is why it wasn't
   done unattended.
2. **Delisted prices** from Tiingo (free tier, API key needed) or CRSP
   (academic) for the bankruptcies and cash acquisitions. With those, the
   delisting-return sensitivity becomes meaningful.
3. **A like-for-like liquid-40 benchmark** (equal weight of the same 40
   names), so breadth and survivorship can be split cleanly.

## Reproduce

```bash
git clone https://github.com/fja05680/sp500 /tmp/sp500 && git -C /tmp/sp500 checkout a2430f2
python build_universe_us.py /tmp/sp500   # membership, Yahoo download (cache/pit/), coverage
python test_universe.py
python run_regimes_pit.py                # -> results/pit_us/curves/, comparison.csv
```
