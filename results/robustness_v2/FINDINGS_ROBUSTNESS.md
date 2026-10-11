# Robustness under engine v2 (HYPOTHESES.md H7)

| Test | Result |
|---|---|
| **H7a** parameter sweep (the old "1 of 96") | **Pass.** 40 of 96 combinations beat buy & hold under v2, against 1 of 96 under v1. In-sample, so this is a statement about the bug, not a tradable result. |
| **H7b** transaction costs 0–50 bps | **Robust null.** The bull/bear interaction is insignificant at every cost level. There is **no break-even**: momentum trails buy & hold even at zero cost. |
| **H7c** max-drawdown bootstrap | **Not reliably shallower.** P(momentum's max DD is shallower than buy & hold's) is 0.43–0.55, and every CI spans 0. |

## H7a — the 96-combination sweep (`sweep_96.csv`)

US 37 names, 2015–2024. These are single in-sample backtests per
combination: lookback {126, 189, 252, 315} × skip {0, 10, 21, 42} ×
fraction {0.1, 0.2, 0.3} × monthly/quarterly. The v1 rerun reproduces the
published `sensitivity_results.csv` (correlation of total returns
0.99999, maximum difference 3.3 percentage points of total return).

| | v1 rerun | v2 |
|---|---|---|
| Beat buy & hold's total return (+1,255%) | **1 / 96** (as published) | **40 / 96** |
| Beat buy & hold's Sharpe (1.19) | 5 / 96 | 25 / 96 |
| Max DD shallower than buy & hold's (−41.4%) | 95 / 96 | 95 / 96 |
| Median total return | +301% | +1,123% |
| Median Sharpe | 0.82 | 1.13 |
| Mean invested fraction | 0.67 | 0.89 |

The published "only 1 of 96 parameter sets beats buy & hold" was a
property of the idle-cash bug, which handicapped every set. Under v2,
about 40% of sets beat buy & hold *in-sample*. The walk-forward, which
chooses parameters without hindsight, still doesn't (README_v2 §1).

## H7b — flat one-way costs (`cost_sensitivity.csv`)

The setup is the US regime-study walk-forward (12-combination grid,
2005–2024, engine v2). The default friction model is replaced by a flat
one-way cost, which also applies while the walk-forward selects
parameters. Buy & hold pays the same cost.

| One-way cost | Momentum CAGR | B&H CAGR | Gap | Momentum Sharpe | B&H Sharpe | Momentum max DD | Interaction / day | 95% CI |
|---|---|---|---|---|---|---|---|---|
| 0 bp | 27.7% | 29.7% | −2.0 | 1.07 | 1.19 | −35.7% | −0.022% | [−0.135, +0.075] |
| 5 bp | 27.3% | 29.7% | −2.4 | 1.06 | 1.19 | −35.7% | −0.016% | [−0.132, +0.081] |
| 10 bp | 26.9% | 29.7% | −2.8 | 1.05 | 1.19 | −35.8% | −0.016% | [−0.132, +0.081] |
| 20 bp | 26.1% | 29.7% | −3.5 | 1.03 | 1.19 | −35.9% | −0.016% | [−0.133, +0.080] |
| 30 bp | 24.7% | 29.7% | −5.0 | 0.98 | 1.19 | −36.0% | −0.020% | [−0.135, +0.076] |
| 50 bp | 22.2% | 29.7% | −7.5 | 0.91 | 1.19 | −37.2% | −0.012% | [−0.126, +0.088] |

Each 10 bp of one-way cost costs momentum about 1 to 1.5 CAGR points
(about 1.5 at the high end). The regime conclusion doesn't move. No
break-even exists in the range: momentum doesn't beat buy & hold on this
universe even when trading is free.

## H7c — max-drawdown distribution (`mdd_bootstrap.json`)

Paired moving block bootstrap: the same resampled blocks for both series,
5,000 draws.

| Sample, block | Point max DD, mom / B&H | Bootstrap median, mom / B&H | 95% CI of (mom − B&H) | P(mom shallower) |
|---|---|---|---|---|
| US regime study 2009–24, 20 d | −35.9% / −45.9% | −37.3% / −36.5% | [−15.0, +14.1] pp | 0.43 |
| US regime study 2009–24, 60 d | −35.9% / −45.9% | −36.3% / −36.6% | [−12.8, +16.5] pp | 0.46 |
| US 2015–24, 20 d | −36.6% / −41.4% | −32.6% / −32.7% | [−14.2, +16.8] pp | 0.50 |
| US 2015–24, 60 d | −36.6% / −41.4% | −36.6% / −33.1% | [−10.0, +21.1] pp | 0.55 |

The realised gap (momentum's max DD 5–10 points shallower) is one draw
from a distribution centred near zero. Momentum's realised max drawdown
is lower than buy & hold's, but the bootstrap gives no evidence that this
is a property of the strategy rather than luck.

Reproduce with `python run_robustness_v2.py` (stages sweep, costs, mdd,
analyze).
