# Short-term reversal vs momentum, by regime (engine v2)

**Short answer:** no regime-dependent difference between reversal and
momentum, or between reversal and buy & hold, survives a multiple-testing
correction in any of the three markets. Of the 24 pre-registered tests,
**0 are significant after Holm adjustment**. 3 are significant before
correction, about what chance alone would produce (24 × 5% ≈ 1.2). The
liquidity-provision hypothesis, that reversal earns more over buy & hold
in high-volatility markets (Nagel 2012), finds no support: the point
estimate has the predicted sign in all three markets, but p = 0.62–0.73.
After costs, reversal underperforms buy & hold over 2009–2024 in all three
markets and is less efficient than momentum in the US.

## Setup

- **Strategy** (`quantbt/strategies/reversal.py`): long the bottom
  fraction by trailing `lookback`-day return, optionally skipping the last
  day; monthly rebalance. Implemented as `CrossSectionalMomentum` with the
  score negated, so `momentum.py` is unchanged. `test_reversal.py` checks
  that it picks a name that just crashed and that, with the sign flipped
  back, it selects exactly momentum's names.
- **Grid:** lookback {5, 10, 21} × skip {0, 1} × fraction {0.1, 0.2},
  12 combinations, the same size as momentum's reduced grid.
- **Everything else is the same as momentum v2:** engine v2,
  `VolatilityTargetSizer`, broker frictions, 4y/1y walk-forward with
  Sharpe selection over 16 folds, and the same warm-up, so both trade the
  same out-of-sample days (2009-01-05 to 2024-12-30, 4,024 days). SPY
  regimes are unchanged.
- **Same data snapshot:** buy & hold v2 rerun on the local price cache
  reproduces `results/v2/curves/` exactly (max abs daily difference
  < 1e-12, `data_check.csv`). Momentum v2 and buy & hold v2 are read from
  `results/v2/curves/` and not rerun.
- **Test family, fixed in `run_regimes_reversal.py` and committed before
  the run** (commit "Short-term reversal strategy and regime study script
  (pre-registered tests)"). Per universe:
  - T1: reversal − B&H, bullish vs bearish.
  - T2: reversal − B&H, high vs low vol.
  - T3: reversal − momentum, bullish vs bearish.
  - T4: reversal − momentum, high vs low vol.
  - T5: reversal − momentum, mean ≠ 0 within each of the four regimes.

  That makes 8 tests × 3 universes = 24. Each uses a moving block
  bootstrap (20-day blocks, 5,000 iterations, seed 0) with a two-sided
  bootstrap p-value. Holm adjustment is applied across all 24 at a 5%
  family-wise error rate.

## Results

### Headline, common out-of-sample window (`headline_metrics.csv`)

| Universe | Strategy | CAGR | Sharpe | Max DD |
|---|---|---|---|---|
| US | Reversal | 17.6% | 0.82 | −46.3% |
| | Momentum | 27.2% | 1.06 | −35.9% |
| | Buy & hold | 29.7% | 1.19 | −45.9% |
| Europe | Reversal | 12.6% | 0.66 | −49.8% |
| | Momentum | 10.8% | 0.61 | −35.6% |
| | Buy & hold | 12.8% | 0.78 | −31.3% |
| Emerging | Reversal | 7.6% | 0.40 | −72.0% |
| | Momentum | 7.1% | 0.38 | −51.9% |
| | Buy & hold | 12.6% | 0.60 | −41.6% |

Buy & hold has the best Sharpe everywhere. Reversal has the deepest
drawdown everywhere.

### Like-for-like check (`invested_fraction.csv`)

PLAN.md flagged that idle cash could make "reversal underperforms" mean
"the sizer leaves reversal in cash". Under engine v2 that isn't the case.
Mean invested fraction is 0.959 / 0.950 / 0.944 for reversal against
0.986 / 0.972 / 0.976 for momentum (US / Europe / Emerging). The gap is
2–3 points, and up to about 7 points in high-vol bear markets.

### Costs (`cost_diagnostic.csv`)

These come from single full-period runs at each strategy's most-chosen
parameters. The walk-forward doesn't expose per-fold costs.

| Universe | Reversal params | Reversal costs / yr | Momentum costs / yr |
|---|---|---|---|
| US | 5d, skip 1, 20% | 0.75% | 0.24% |
| Europe | 5d, skip 0, 20% | 0.99% | 0.26% |
| Emerging | 5d, skip 0, 10% | 2.31% | 0.67% |

Costs are commission plus slippage, as a share of average equity. Reversal
pays 3–4 times momentum's costs. That is a meaningful drag but doesn't
explain the whole US shortfall against momentum (9.6 points of CAGR).

The walk-forward almost always picks the 5- or 10-day lookback: 15 of 16
US folds and 13 of 16 Emerging folds. In Europe, 8 of 16 folds pick
5–10 days and the other 8 pick 21 days.

### Annualised return by regime (`breakdown.csv`)

| Universe | Strategy | Bull, low vol | Bull, high vol | Bear, low vol | Bear, high vol |
|---|---|---|---|---|---|
| US | Reversal | 29.4% | 86.0% | −56.3% | −31.4% |
| | Momentum | 44.0% | 92.3% | −57.0% | −33.1% |
| | Buy & hold | 47.9% | 101.4% | −72.1% | −29.3% |
| Europe | Reversal | 14.5% | 66.9% | −41.0% | −5.4% |
| | Momentum | 16.4% | 95.3% | −48.6% | −26.6% |
| | Buy & hold | 15.1% | 92.4% | −40.4% | −13.6% |
| Emerging | Reversal | 3.3% | 73.1% | −26.3% | 9.7% |
| | Momentum | 5.2% | 118.8% | −46.0% | −9.2% |
| | Buy & hold | 12.3% | 91.5% | −57.3% | 2.8% |

### The 24 tests (`interaction_significance.csv`)

All values are mean daily differences.

| Universe | Test | Estimate | 95% CI | p | p (Holm) |
|---|---|---|---|---|---|
| US | T1 rev−B&H, bull vs bear | −0.071% | [−0.170, +0.026] | 0.147 | 1.00 |
| US | T2 rev−B&H, high vs low vol | +0.025% | [−0.068, +0.113] | 0.622 | 1.00 |
| US | T3 rev−mom, bull vs bear | −0.056% | [−0.177, +0.067] | 0.392 | 1.00 |
| US | T4 rev−mom, high vs low vol | +0.045% | [−0.068, +0.154] | 0.477 | 1.00 |
| US | T5 rev−mom in bull/low | **−0.046%** | [−0.089, −0.005] | **0.024** | 0.59 |
| US | T5 rev−mom in bull/high | −0.024% | [−0.200, +0.127] | 0.601 | 1.00 |
| US | T5 rev−mom in bear/low | +0.005% | [−0.199, +0.168] | 0.958 | 1.00 |
| US | T5 rev−mom in bear/high | +0.014% | [−0.116, +0.153] | 0.834 | 1.00 |
| Europe | T1 | −0.044% | [−0.118, +0.034] | 0.261 | 1.00 |
| Europe | T2 | +0.012% | [−0.056, +0.075] | 0.730 | 1.00 |
| Europe | T3 | **−0.114%** | [−0.219, −0.005] | **0.040** | 0.89 |
| Europe | T4 | +0.056% | [−0.034, +0.146] | 0.210 | 1.00 |
| Europe | T5 bull/low | −0.007% | [−0.038, +0.026] | 0.684 | 1.00 |
| Europe | T5 bull/high | −0.062% | [−0.163, +0.030] | 0.170 | 1.00 |
| Europe | T5 bear/low | +0.050% | [−0.235, +0.169] | 0.922 | 1.00 |
| Europe | T5 bear/high | **+0.112%** | [+0.010, +0.226] | **0.033** | 0.76 |
| Emerging | T1 | −0.092% | [−0.218, +0.039] | 0.164 | 1.00 |
| Emerging | T2 | +0.026% | [−0.081, +0.127] | 0.646 | 1.00 |
| Emerging | T3 | −0.115% | [−0.273, +0.057] | 0.188 | 1.00 |
| Emerging | T4 | +0.027% | [−0.111, +0.156] | 0.694 | 1.00 |
| Emerging | T5 bull/low | −0.007% | [−0.065, +0.047] | 0.803 | 1.00 |
| Emerging | T5 bull/high | −0.100% | [−0.302, +0.069] | 0.206 | 1.00 |
| Emerging | T5 bear/low | +0.132% | [−0.219, +0.537] | 0.438 | 1.00 |
| Emerging | T5 bear/high | +0.093% | [−0.078, +0.261] | 0.257 | 1.00 |

## Reading it

- **Nothing survives the correction.** The three raw hits are
  reversal lagging momentum in US calm bull markets, a bull/bear
  interaction against momentum in Europe, and reversal beating momentum
  in European high-vol bear markets. None comes close after Holm: the
  smallest adjusted p is 0.59. Three hits in 24 is what noise produces.
- **There is a consistent pattern in the point estimates, but it isn't
  evidence.** Reversal − momentum is negative in all three markets in
  bullish regimes and positive in all three in high-vol bear markets.
  T3's sign is the same in all three (reversal does relatively worse in
  bull markets than in bear markets). That fits the textbook story that
  momentum crashes and reversal pays in stressed rebounds. But each test
  is individually weak, the three markets share the SPY regime calendar
  and much of their global shocks, and they are not three independent
  confirmations.
- **The Nagel prediction (T2) fails to show.** Reversal's edge over
  buy & hold is a little higher in high-vol regimes everywhere (+0.012%
  to +0.026% a day), but the CIs are many times wider than the
  estimates.
- **As a strategy, reversal is not competitive here.** It has a lower
  Sharpe than buy & hold in all three markets, and the deepest drawdowns,
  with Emerging at −72%. The universe is 37–38 large, liquid names, where
  short-term reversal is known to be weak after costs. PLAN.md flagged a
  null as a plausible outcome.

## Caveats

- Same fixed, present-day universes as the rest of the study, so the same
  survivorship bias. It is shared by all three strategies, which keeps
  the comparison like-for-like.
- 4–8 holdings, so idiosyncratic noise is large.
- The cost diagnostic uses modal parameters, not the walk-forward's actual
  per-fold choices.
- The regime calendar is SPY's for all three markets, inherited from the
  published design.

## Files

| Path | What |
|---|---|
| `run_regimes_reversal.py` | Stages check → runs → analyze; the test family is in its docstring |
| `data_check.csv` | Buy & hold v2 rerun vs `results/v2` (identical) |
| `curves/regime_*_wf_reversal_v2.csv`, `*_folds.csv` | Reversal walk-forward curves and fold choices |
| `headline_metrics.csv`, `invested_fraction.csv`, `cost_diagnostic.csv` | Tables above |
| `breakdown.csv`, `returns_detail.csv` | Per-regime metrics; daily returns of all three strategies with regime labels |
| `interaction_significance.csv` | The 24 tests: raw and Holm p-values |
