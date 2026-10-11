# Point-in-time S&P 500 from 2000: the dot-com bust (HYPOTHESES.md H8)

**Short answer.**

- **H8a passes:** over 2000–2024, momentum's bull/bear interaction against
  the PIT equal-weight benchmark is **+0.082% a day, 95% CI
  [+0.023%, +0.130%]**. Momentum does relatively worse in bear markets.
  That is more clearly significant than on 2009–2024 alone, and the same
  sign.
- **H8b:** momentum did **not** protect in the dot-com bust. It lost
  27.1% against the benchmark's 10.4%, with a deeper max drawdown
  (−34.7% against −32.4%).
- Across the GFC the two lost about the same (−54.7% against −57.0%).
  Then came the 2009 rebound: momentum +11.5% against the benchmark's
  +45.4%. That is Daniel & Moskowitz's momentum crash, visible in this
  data.

## Data and coverage

- **Membership:** fja05680/sp500 (commit `a2430f2`), 1996–2024, 1,175
  distinct tickers. The verified rename map (`data/sp500_rename_map.csv`)
  is applied.
- **Prices:** Yahoo, from 1996.
- **Walk-forward:** 4y/1y, so trading runs 2000–2024 (25 folds).
- **Regimes:** SPY regimes computed from 1993.

| | Coverage of member-days (before rename map) |
|---|---|
| 1996–2024 overall | 65.5% |
| 1996 | 37.9% |
| **2000–2004** | **≈ 50%** (2000: 46.7%, 2002: 49.9%, 2004: 52.0%) |
| 2009 | 62.2% |
| 2024 | 95.7% |

The pre-registered blocking rule flags any year below 40%. 2000–2004 is
above it, so those years are reported normally, but about half of
member-days are missing. The missing names are disproportionately the
dot-com failures, and momentum held many of them on the way up. The
dot-com numbers are therefore **likely too favourable to momentum**.
1996–1999 is training data only.

## Results (`h8_result.json`, `yearly_returns.csv`)

| Period | Momentum CAGR | Sharpe | Max DD | Benchmark CAGR | Sharpe | Max DD |
|---|---|---|---|---|---|---|
| 2000–2024 | 9.2% | 0.51 | −55.0% | 10.6% | 0.61 | −57.4% |
| 2000–2008 | 2.1% | 0.21 | −50.0% | 3.7% | 0.28 | −54.7% |
| 2009–2024 | 13.4% | 0.71 | −36.0% | 14.7% | 0.82 | −37.4% |

The 2009–2024 rows differ slightly from `results/pit_us_renamed` (14.0%
and 14.0%). This build starts in 1996, so walk-forward folds are trained
on different years, and its reused-ticker check excludes 10 names instead
of 5.

| Window | Momentum return | Max DD | Benchmark return | Max DD |
|---|---|---|---|---|
| Dot-com, 2000-03-24 → 2002-10-09 | −27.1% | −34.7% | −10.4% | −32.4% |
| GFC, 2007-10-09 → 2009-03-09 | −54.7% | −54.5% | −57.0% | −57.0% |

| Year | 2000 | 2001 | 2002 | 2003 | 2008 | 2009 |
|---|---|---|---|---|---|---|
| Momentum | 0.0% | +5.9% | −17.7% | +43.7% | −41.2% | +11.5% |
| Benchmark | +16.4% | +4.8% | −14.6% | +37.1% | −37.0% | +45.4% |

| Interaction (bull − bear, /day) | Bullish gap | Bearish gap | Interaction | 95% CI |
|---|---|---|---|---|
| 2000–2024 | +0.019% | −0.063% | **+0.082%** | **[+0.023, +0.130]** |

## Reading it

- **The dot-com bust is no exception to the pattern.** Momentum entered
  2000 holding the technology winners and lagged the equal-weight index
  by 16 points in 2000 alone, while equal weight's tilt to old-economy
  names held up. Missing data probably understates the damage.
- **2009 is the textbook momentum crash.** Momentum went into the rebound
  holding defensive late-2008 winners and missed a 45% recovery by 34
  points.
- **Over 25 years**, momentum trails the equal-weight S&P 500 by 1.4 CAGR
  points, with a lower Sharpe. Its bull/bear interaction is positive and
  significant. Across a sample that now includes two crashes and two
  rebounds, the evidence is the opposite of "drawdown protection".

Reproduce: `python run_pit_2000.py /path/to/fja05680-sp500-clone`
(downloads 1996+ prices into `cache/pit1996/`).
