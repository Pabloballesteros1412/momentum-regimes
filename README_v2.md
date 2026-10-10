# Momentum's Drawdown Protection Was Mostly Idle Cash

*Draft. This is the corrected version of `README.md`, rebuilt on engine v2. `README.md` and its CSVs are left untouched as the published record. The "Correction" section explains what changed and why.*

An event-driven backtesting engine built from scratch, used to test whether cross-sectional momentum's regime-dependent behaviour replicates outside the United States.

The first version of this project reported that momentum cushions US drawdowns. That result came from a sizing bug: the engine left exit proceeds in cash until the next rebalance, so the momentum book ran at about two-thirds equity exposure. With the bug fixed, the US bull/bear asymmetry can no longer be distinguished from zero. Europe still shows a small effect in the opposite direction, and emerging markets show nothing. One real episode survives: in 2022, momentum's drawdown was less than half of buy & hold's.

## Motivation

Cross-sectional momentum is one of the most documented anomalies in asset pricing, and a common claim about it is that it cushions equity drawdowns: the strategy rotates out of falling names and into whatever is still holding up. Most of the evidence behind that claim comes from US data.

This project builds the infrastructure needed to test the claim properly, then applies it to three universes over 2005-2024.

## Implementation

The engine is written in plain Python with pandas and numpy. No vectorbt, no backtrader. The point was to control the execution model rather than inherit someone else's assumptions about it.

```
quantbt/
├── data/        point-in-time bar delivery from cached yfinance data
├── engine/      event objects, simulated broker, the main loop
├── strategies/  Strategy base class, buy & hold, cross-sectional momentum, short-term reversal
├── risk/        position sizing (equal weight, volatility targeting), engine v1/v2 batch sizing
├── portfolio/   position and cash bookkeeping, equity curve
├── analytics/   metrics, tearsheet, regime classification, significance tests, JSON export
└── validation/  walk-forward analysis, stress testing
```

### Execution model

A vectorised backtest computes signals across the whole price series at once. It is fast, and it makes look-ahead bias easy to introduce without noticing, because the array holding day 10 already contains day 500.

This engine advances a clock one bar at a time. A strategy can only reach data through `get_latest_bars()`, which is capped at the current timestamp. There is no API path to future rows. Orders raised on bar *t* fill at the open of bar *t+1*, after slippage and commission.

Three frictions are modelled: a one-bar execution delay, square-root market impact scaled by participation rate, and per-share commission with a minimum. Orders are also capped at 10% of trailing average volume, so the backtest cannot pretend to move size the market would not absorb.

On a rebalance day, engine v2 sizes the whole batch at once. Proceeds from exits and trims are credited, at a 2% haircut, before any buy is capped. If the buys still exceed cash, they are scaled down pro rata. Sells settle before buys, and a buy the account can't afford at its actual fill is trimmed, so cash never goes negative. Engine v1, which produced the published numbers, did none of this (see "Correction").

## Data and methodology

**Strategy.** Cross-sectional momentum, 12-1: rank the universe by trailing 252-day return excluding the most recent 21 days, hold the top decile, rebalance monthly. The one-month skip is standard, because short-horizon reversal contaminates the signal.

**Sizing.** Volatility targeting: each name gets weight min(15% / realised vol, 35%). Every name under about 43% annualised vol gets the 35% cap, and a 60%-vol name gets 25%. With four or more names, the weights usually sum to more than 100%; in the US this happened at 97% of rebalances. In that case engine v2's cash cap scales the buys down, so the book ends up close to fully invested.

**Validation.** Walk-forward with a four-year training window and a one-year trading window. Within each training window a parameter grid is swept and the best Sharpe is selected; those parameters then trade the following year without reoptimisation. Only the trading windows are concatenated into the reported equity curve. Two different grids are used in this project, not one: the single-universe validation in Results §1-2 sweeps the full 96-combination grid (four lookbacks, four skip windows, three fractions, two rebalance frequencies) over six folds, 2015-2024; the three-universe regime analysis in §3 onward sweeps a reduced 12-combination grid (three lookbacks, two skips, two fractions, rebalance frequency held at monthly) over sixteen folds, 2005-2024, so that three markets over twenty years stays tractable. Every number below is traceable to one or the other.

**Regimes.** Each day is classified on two axes using SPY as reference: trend (above or below the 200-day moving average) and volatility (21-day realised vol above or below its expanding 75th percentile). The expanding percentile matters. A percentile computed over the full sample would use 2024 information to label a day in 2005.

**Significance.** Block bootstrap with a 20-day block and 5,000 iterations, plus an effective sample size adjusted for autocorrelation. Regimes arrive in contiguous runs and a monthly-rebalanced strategy adds its own serial correlation, so resampling individual days would treat dependent observations as independent and produce confidence intervals that are far too narrow.

**Data snapshot.** All v2 numbers come from one Yahoo Finance download (October 2026). Before any v2 run, buy & hold was rerun on that download and compared with the stored published returns. Correlation was 1.0000 in all three universes, cumulative returns matched within 0.2 percentage points, and the SPY regime labels matched on every day. Every v2 result is compared against a v1 rerun on the same download, so data drift can't pass for an effect.

## Results

### 1. Effect of out-of-sample validation

The first version of the momentum backtest returned 1,330% over 2015-2024. Three things were wrong with that number.

The volatility-target sizer computed each position's weight independently and never checked the sum. When the top decile held four names and each was allocated 30%, the book ran at 120% exposure. The fix capped buys at available cash, filled first-come in alphabetical order, which brought the figure to 522%. That fix introduced the third problem: exit proceeds weren't available to that day's buys, so the book carried idle cash between rebalances. Engine v2 fixes that.

| | Total return | Max drawdown |
|---|---|---|
| Momentum, in-sample | +1,559.16% | -32.41% |
| Momentum, walk-forward | +419.89% | -36.58% |
| Buy & hold | +1,254.81% | -41.35% |

Walk-forward validation still costs most of the in-sample figure: 1,139 percentage points, the price of having chosen parameters with hindsight. The strategy still did not beat the benchmark out of sample, but the gap is far smaller than published: 835 points rather than 1,077.

### 2. Drawdown behaviour in the US universe

Isolating specific windows separates two behaviours that the regime averages hide.

| Window | Strategy | Return | Max DD | Days to recover |
|---|---|---|---|---|
| COVID crash (Feb-Mar 2020) | Momentum WF | -17.54% | -36.58% | 124 |
| | Buy & hold | -13.46% | -30.27% | 107 |
| 2022 bear market | Momentum WF | +0.43% | -18.67% | 530 |
| | Buy & hold | -33.68% | -40.15% | 525 |

In 2022 momentum ended the window flat while the benchmark lost a third. Its drawdown was less than half the benchmark's under both engine versions, so this episode reflects what momentum held, not idle cash. Its recovery took about as long as the benchmark's (530 days against 525).

In the COVID crash momentum lost more than the benchmark, and its drawdown was deeper. But it recovered in 124 days against the benchmark's 107, not the 378 days originally reported. Most of that long recovery was idle cash after the March 2020 rebalances, not a strategy stuck in defensives. The crash itself still matches the momentum-crash mechanism described by Daniel and Moskowitz (2016): entering February 2020 the portfolio held whatever had risen most over the prior twelve months, which was exactly what fell hardest. The second half of the original story, missing the rebound, doesn't survive the fix.

So momentum protected in one of the two US crashes and did worse in the other. That is a story about two episodes. It is not evidence of a systematic regime effect, which §3 tests directly.

### 3. Cross-market replication

Annualised returns by regime, walk-forward momentum, 2005-2024 (engine v2):

| Universe | Bullish, low vol | Bullish, high vol | Bearish, low vol | Bearish, high vol |
|---|---|---|---|---|
| US | 44.03% | 92.26% | -57.04% | -33.06% |
| Europe | 16.45% | 95.27% | -48.56% | -26.60% |
| Emerging | 5.17% | 118.76% | -46.01% | -9.20% |

Comparing regime against regime within one strategy is close to tautological: every strategy earns less in bear markets, and a fully invested book earns less still. The relevant test is whether the *gap* between momentum and buy & hold changes with the regime.

| Universe | Mean daily gap, bullish | Mean daily gap, bearish | Difference | 95% CI | Verdict |
|---|---|---|---|---|---|
| US | -0.009% | +0.007% | -0.015% | [-0.132%, 0.082%] | Not significant |
| Europe | +0.007% | -0.063% | +0.070% | [0.003%, 0.136%] | Significant |
| Emerging | -0.012% | -0.035% | +0.023% | [-0.099%, 0.141%] | Not significant |

The US gap keeps its sign but shrinks to an eighth of its published size, and its confidence interval now spans zero. Europe still points the other way and stays just significant: in European bear markets, momentum did worse than buy & hold. Emerging markets cannot be distinguished from noise.

The European result should not be oversold. Its lower bound sits at 0.003%, essentially touching zero, and the bearish side rests on about 709 days out of sixteen years. It is a weak signal in the opposite direction, not a clean counterexample. What the data supports is that momentum has no detectable regime-dependent edge over buy & hold in any of the three markets, once it is fully invested. Europe's opposite-direction effect is the only thing the significance test picks up.

### Attribution of cross-market divergence

With the US effect gone, there is less divergence to explain. The original attribution analysis (sector composition across 33 bearish rebalances, parameter selection by fold) was run on engine v1 portfolios, and its sector shares were not recomputed under v2.

One input has changed. Under v1, Europe picked the more concentrated top-decile fraction in 62.5% of folds against 50% in the US. Under v2 the order reverses: 31.25% against 37.5%. The concentration explanation offered for Europe's opposite-direction result no longer has the sign it needs.

### Distributional properties of returns

*`tearsheet.png` shows the engine v1 curves and has not been regenerated. The figures below come from the v2 curves (`results/v2/curves/`).*

Jarque-Bera rejects normality at p < 0.001 for every equity curve, with excess kurtosis of 7.3 for walk-forward momentum and 6.1 for buy & hold. The Sharpe ratios below therefore rest on an assumption the data contradicts. Standard deviation understates risk when it lives in the tails.

The walk-forward strategy's max drawdown (-36.58%) is still shallower than buy & hold's (-41.35%), and it recovers far faster (124 days against 571). Its Calmar ratio (0.87) now beats buy & hold's (0.72). Sharpe (1.13 against 1.19), Sortino (1.61 against 1.72) and 95% CVaR (-4.09% against -3.66% daily) still favour buy & hold. Under v2 the story is mixed in a different way from the published one. Momentum has the better drawdown profile, buy & hold the better day-to-day risk-adjusted return, and neither dominates.

The US market spends about 79% of days in a bullish regime. Under v1 that made the published "insurance premium" look expensive: momentum lagged on the many bullish days and cushioned on the few bearish ones. Under v2 there is no premium and no payout to speak of. The gap is close to zero in both regimes.

## Correction

### What was wrong

Engine v1 reserved the account's cash at the start of each bar, before that bar's exit orders settled, and never credited sell proceeds back to the batch. On every rebalance day, new entries could only use cash that was already idle. The proceeds from names leaving the portfolio sat uninvested until the next rebalance, a month or a quarter later. When the buys exceeded cash, the alphabetically later tickers were the ones starved.

The published US walk-forward book was on average 67% invested. On bearish days that fell to 58%. Cash doesn't fall in a bear market, so a book that is a third cash lags in bull markets and cushions in bear markets by construction. That alone reproduces the published pattern. From the published returns alone, a constant 67% buy & hold / 33% cash portfolio reproduces 93% of the US regime interaction (`results/v2/beta_diagnostic.csv`).

The README also misdescribed two things. It said the sizer was fixed to "normalise weights across concurrent signals"; it did sequential cash capping in ticker order instead. It also said a 60%-vol name receives "roughly a third of the capital of one realising 20%"; with the 35% weight cap the ratio is about 0.71.

### How it was tested

Engine v2 is opt-in (`engine_version="v2"` on the sizer), and the default path is unchanged. A regression test reproduces 5,878 rows written by the engine *before* v2 existed, bit for bit (`test_engine_v2.py`). Then every published configuration was rerun on one data snapshot under v1 and under v2 (bug fixed). The v1 rerun reproduces the published numbers exactly, so every v1-to-v2 difference comes from the engine.

The decision rule was written before the reruns (`results/v2/FINDINGS_CASH.md`). For the US regime interaction, *retained* is the v2 gap divided by the v1 gap:

| Verdict | Condition |
|---|---|
| Survives | Same sign, 95% CI still excludes 0, retained ≥ 2/3 |
| Weakened | Same sign, but the CI includes 0 or retained is between 1/3 and 2/3 |
| Does not survive | Retained < 1/3, or the sign flips |

The 2022 window also had to hold: momentum's max drawdown had to stay shallower than buy & hold's.

### How the conclusion changed

| | US bull − bear gap | 95% CI | Retained | 2022 max DD | Verdict |
|---|---|---|---|---|---|
| Published (v1) | -0.122% | [-0.244%, -0.011%] | — | -18.24% | — |
| v2 | -0.015% | [-0.132%, 0.082%] | 0.12 | -18.67% | **Does not survive** |

Invested fraction for the US walk-forward book rose from 0.67 to 0.98. Its beta to buy & hold rose from 0.67 to 0.87. Europe's opposite-sign interaction survives v2. Emerging markets stay null.

The original title, "Momentum's Drawdown Protection Is a US Phenomenon", is withdrawn. The US result came from the engine, not from the market.

A third variant, v2full, also scales the book up to 100% gross whenever vol targeting leaves it under-invested. It is reported in an appendix (`results/v2full_fix/FINDINGS_V2FULL.md`), not here. An early version of `full_investment` also scaled over-100% books *down*, which left v2full less invested than v2 and briefly made its verdict "Weakened". After that was fixed, v2full is identical to v2 in the US, because every US rebalance already summed past 100%. Its verdict is also "Does not survive". v2 is the main result because it changes only the bug.

## Limitations

**The universes are not point-in-time.** All three are fixed, current ticker lists. Companies that delisted or went bankrupt never enter the sample, which inflates both the strategy and the benchmark. Building this properly requires historical index constituents, which are commercial data outside the US. The emerging universe illustrates the problem directly: several ADRs are absent because of geopolitical delisting, which is survivorship bias visible in the dataset itself.

**The momentum book is still not a pure factor.** Under v2 the book is close to fully invested, but its beta to buy & hold is 0.87 in the US, 0.92 in Europe and 0.77 in emerging markets. It holds four to eight names, so idiosyncratic risk is large.

**One period, one strategy family.** Twenty years, one implementation of one factor. Nothing here says anything about momentum in other decades or about other factors.

**The four-regime scheme collapses to two.** Low-volatility and high-volatility bear markets were statistically indistinguishable in every universe and for both strategies in the published analysis. The volatility axis adds no separation at this sample size.

**Nothing here is an allocation rule.** The results describe how a factor behaved in specific markets over a specific window. Choosing a strategy based on an expected market environment is market timing, and this project provides no evidence that market timing works.

## Reproducing the results

```bash
pip install -r requirements.txt

python test_pipeline.py      # synthetic-data smoke test, no network required
python test_engine_v2.py     # v1 path bit-for-bit vs pre-v2 fixture; v2 solvency and timing

# Engine v2 reruns of every published configuration, with drift check
python run_cash_v2.py        # -> results/v2/ (drift, v1/v2/v2full curves, comparison tables)
python run_v2full_fix.py     # -> results/v2full_fix/ (appendix: v2full after the scale-up-only fix)
```

The published v1 scripts (`run_walkforward.py`, `run_regimes.py`, and the rest) still reproduce `README.md`. Note that `run_regimes.py` and the significance scripts overwrite the published CSVs when run.

Price data is cached as parquet under `cache/` on first download, so subsequent runs need no network access.

## References

Daniel, K. and Moskowitz, T. (2016). Momentum crashes. *Journal of Financial Economics*, 122(2), 221-247.

Jegadeesh, N. and Titman, S. (1993). Returns to buying winners and selling losers. *Journal of Finance*, 48(1), 65-91.
