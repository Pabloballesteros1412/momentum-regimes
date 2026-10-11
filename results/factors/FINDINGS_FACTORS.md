# Fama-French 5 factors + momentum (HYPOTHESES.md H5)

**Short answer.**

- **The engine reproduces the academic momentum factor.** Every momentum
  book loads strongly on UMD. On the point-in-time S&P 500, the active
  return (momentum − benchmark) correlates **0.71** with UMD monthly.
- **No momentum book has alpha beyond the factors**, on the
  point-in-time universe or in its active return.
- **The fixed 37-name list's apparent alpha belongs to the list, not the
  strategy.** Buy & hold of those names alone shows **+11.8% a year of
  FF5+UMD alpha (t = 4.4)**. That is look-ahead in the universe choice,
  measured directly.

Verdicts:

| Hypothesis | Result |
|---|---|
| H5a (US v2 positive UMD loading, t > 2) | **Pass** (0.54, t = 21.9) |
| H5a-PIT | **Pass** (0.46, t = 29.7) |
| H5d (v2 market beta > v1 everywhere) | **Pass** (US 0.94 → 1.15, Europe 0.67 → 0.78, Emerging 0.94 → 1.14) |

## Data and method

French data library, downloaded 2026-10-11 (`data/ff/`). US: 5 factors
(2×3) and momentum, daily. Europe: 5 factors and momentum, daily, in USD.
Emerging: 5 factors and momentum, **monthly only**. The model is OLS of
r − RF on MKT, SMB, HML, RMW, CMA and UMD, with Newey-West standard errors
(10 lags daily, 3 monthly). Sample: 2009–2024 out of sample, 4,024 US
days, 4,133 Europe days, 192 Emerging months. Alpha is annualised.

## Loadings (`regressions.csv`)

| Universe | Series | α / yr | t(α) | MKT | SMB | HML | RMW | CMA | **UMD** | t(UMD) | R² |
|---|---|---|---|---|---|---|---|---|---|---|---|
| US | Momentum v1 | +3.8% | 1.2 | 0.94 | −0.03 | −0.02 | 0.03 | −0.19 | **0.45** | 17.0 | 0.62 |
| US | Momentum v2 | +10.2% | **2.9** | 1.15 | −0.03 | −0.02 | −0.02 | −0.18 | **0.54** | 21.9 | 0.69 |
| US | Buy & hold (37 names) | **+11.8%** | **4.4** | 1.12 | −0.09 | −0.31 | −0.09 | −0.53 | 0.10 | 6.3 | 0.80 |
| US | PIT momentum (renamed) | −0.3% | −0.2 | 1.08 | 0.09 | 0.04 | −0.12 | 0.14 | **0.46** | 29.7 | 0.88 |
| US | PIT equal-weight benchmark | +0.7% | 0.9 | 0.92 | 0.09 | 0.17 | 0.06 | 0.12 | −0.10 | −13.0 | 0.97 |
| Europe | Momentum v1 | −2.1% | −0.7 | 0.67 | −0.39 | 0.09 | −0.05 | −0.06 | **0.47** | 14.0 | 0.52 |
| Europe | Momentum v2 | +2.2% | 0.8 | 0.78 | −0.44 | 0.08 | −0.01 | 0.12 | **0.58** | 17.7 | 0.65 |
| Europe | Buy & hold | +6.2% | **4.1** | 0.73 | −0.54 | −0.07 | 0.20 | −0.19 | 0.05 | 2.6 | 0.84 |
| Emerging (monthly) | Momentum v1 | −4.8% | −0.8 | 0.94 | 0.21 | −0.38 | −0.91 | 0.66 | **0.81** | 4.8 | 0.36 |
| Emerging (monthly) | Momentum v2 | −2.7% | −0.4 | 1.14 | −0.05 | −0.36 | −1.20 | 1.10 | **0.70** | 4.8 | 0.47 |
| Emerging (monthly) | Buy & hold | +3.8% | 1.2 | 1.09 | −0.21 | 0.02 | −0.48 | 0.10 | 0.20 | 1.9 | 0.77 |

## Active return (momentum − benchmark) vs UMD (`umd_correlation.csv`, `active_regressions.csv`)

| Universe | Series | Corr. with UMD, daily | Corr., monthly | H5b | Active α / yr | t | UMD loading |
|---|---|---|---|---|---|---|---|
| US | v1 − B&H | 0.29 | 0.36 | tracks partly | −8.0% | −2.2 | 0.34 |
| US | v2 − B&H | 0.37 | 0.31 | tracks partly | −1.6% | −0.5 | 0.44 |
| US | **PIT (renamed) − PIT benchmark** | **0.74** | **0.71** | **tracks well** | −1.0% | −0.5 | 0.56 |
| Europe | v1 − B&H | 0.38 | 0.42 | tracks partly | −8.3% | −3.1 | 0.42 |
| Europe | v2 − B&H | 0.46 | 0.33 | tracks partly | −4.0% | −1.7 | 0.52 |
| Emerging | v1 − B&H | — | 0.36 | tracks partly | −9.1% | −1.9 | 0.62 |
| Emerging | v2 − B&H | — | 0.25 | does not track | −7.0% | −1.4 | 0.52 |

## Reading it

- **The engine builds real momentum.** On a broad point-in-time universe
  (about 400–500 rankable names), the active return tracks the
  Fama-French UMD factor at 0.71 monthly. That is high for a long-only,
  top-decile, monthly-rebalanced book with costs against a long-short,
  value-weighted, daily-rebalanced factor. On 37 names the tracking falls
  to 0.3. Four to eight holdings carry a lot of idiosyncratic noise.
- **The idle-cash bug was a large negative alpha.** v1's active alpha is
  −8% a year in the US and Europe (both significant). v2's is −1.6% and
  −4.0%, neither significant. The bug cost about 6 points a year, not
  just beta.
- **v2's 10% US alpha is the universe's, not momentum's.** Buy & hold of
  the same 37 names earns 11.8% a year of alpha. Momentum v2's active
  alpha against that buy & hold is −1.6% (t = −0.5). On the PIT S&P 500,
  momentum's alpha is −0.3% and the benchmark's +0.7%, both
  insignificant, as expected for a portfolio that the factors should
  price.
- **Europe and Emerging behave the same way.** The momentum books load
  strongly on their regional WML factor. Europe's buy & hold has its own
  +6.2% alpha (t = 4.1), the same fixed-list effect. The Emerging
  regressions are monthly, with wide errors.

## Caveats

- Europe's universe mixes USD ADRs with EUR/CHF local listings (no FX
  layer), while the factors are in USD. That mismatch adds noise to the
  European regressions.
- Emerging factors are monthly only.
- The factors are value-weighted and include small caps. Our books are
  large caps. Loadings, not alphas, are the main check here.

Reproduce with `python run_factor_regressions.py`.
