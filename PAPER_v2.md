# Momentum's Drawdown Protection Was Mostly Idle Cash: A Corrected, Point-in-Time Re-examination

*Working paper draft, October 2026. This supersedes the analysis in
`README.md`; the original text and results are kept unchanged in the
repository as the published record.*

## Abstract

An earlier version of this project reported that cross-sectional momentum
cushions US equity drawdowns, and that the effect does not replicate in
Europe or emerging markets. Both claims were produced by a bug in my own
backtesting engine. The engine left the proceeds of every exit in cash
until the next rebalance, so the "momentum" book ran at about two-thirds
equity exposure (beta 0.67). When that is fixed (engine v2), the
published US bull/bear asymmetry shrinks to an eighth of its size and its
confidence interval spans zero. The verdict under a rule written before
the rerun: **does not survive**.

I then rebuild the evidence on firmer ground:

- **A point-in-time S&P 500 universe.** Free data covers 77% of
  member-days, with renamed tickers mapped using SEC EDGAR evidence.
  Survivorship in the original 37-name list roughly halves both
  momentum's and the benchmark's CAGR over 2009–2024 (27% → 14% and
  30% → 14%). On the point-in-time universe the US regime interaction is
  significant again, but in the **opposite** direction: momentum does
  relatively worse in bear markets (+0.075%/day bull minus bear, 95% CI
  [+0.003, +0.152]).
- **The one surviving protective episode, 2022, is a sector bet.**
  Energy and healthcare allocation explains essentially all of it, and it
  is the exception among five US bear markets.
- **The engine reproduces the academic factor.** The point-in-time book's
  active return correlates 0.71 with Fama-French UMD. It has no alpha
  beyond the factors. The fixed 37-name list's buy & hold has 11.8% a
  year of FF5+UMD alpha, which measures the hindsight in choosing it.
- **Short-term reversal is no regime hedge.** None of 24 pre-registered
  reversal-vs-momentum regime tests survive a Holm correction.
- **Volatility scaling cuts momentum's crash drawdowns but not its risk-
  adjusted return.** It halves within-window drawdowns in the 2009
  rebound and COVID, with no Sharpe gain over the full sample.

Every confirmatory test in this paper was written down, with its pass/fail
rule, before it was run (`HYPOTHESES.md`). Exploratory results are
labelled as such.

---

## 1. Motivation

Cross-sectional momentum (Jegadeesh & Titman 1993) is among the best
documented return anomalies. A common practitioner claim is that it
cushions drawdowns: it rotates out of falling names into whatever is
still holding up. The academic record says the opposite about the worst
cases. Momentum crashes in sharp market rebounds after bear markets
(Daniel & Moskowitz 2016), and its risk is predictable enough that
scaling by recent volatility nearly doubles its Sharpe ratio (Barroso &
Santa-Clara 2015).

This project began as an event-driven engine built from scratch, used to
test whether momentum's regime behaviour replicates outside the US. Its
first conclusion, a US-only protective effect, did not survive a review
of the engine. This paper reports that review, the corrected results,
and the evidence I built to replace the original conclusion.

## 2. Engine and methodology

### 2.1 Execution model

The engine (`quantbt/`, plain Python with pandas and numpy) advances one
bar at a time. Strategies can only read data through `get_latest_bars()`,
which is capped at the current timestamp, so there is no API path to
future rows. Orders raised on bar *t* fill at the open of bar *t+1*. The
costs are:

- square-root market impact on participation, plus a 2 bp spread;
- a per-share commission with a minimum;
- a cap of 10% of 20-day average volume on any order.

### 2.2 Strategy, sizing, validation

- **Momentum.** Rank by trailing *L*-day return skipping the last *S*
  days; hold the top fraction *f*; rebalance monthly (or quarterly in the
  96-combination grid).
- **Sizing.** Volatility targeting: weight = min(15% / realised vol, 35%).
  With four or more names, the weights usually sum to more than 100%.
- **Walk-forward.** 4-year training and 1-year trading windows. The best
  training Sharpe across a parameter grid trades the next year unchanged.
  Two grids are used:
  - a 96-combination grid (US 2015–2024, six folds);
  - a 12-combination grid (L ∈ {189, 252, 315}, S ∈ {10, 21},
    f ∈ {0.1, 0.2}; 2005–2024, sixteen folds) for every regime study.

### 2.3 Regimes and inference

Each day gets a two-axis label from SPY:

- **Trend:** SPY above or below its 200-day average.
- **Volatility:** 21-day realised vol above or below its *expanding* 75th
  percentile, so the label never uses future data.

The key statistic is the **interaction**: mean daily (strategy −
benchmark) on bullish days minus the same on bearish days. A positive
value means the strategy does relatively worse in bear markets. Inference
uses a moving block bootstrap (20-day blocks, 5,000 iterations).

### 2.4 Pre-registration

Every test from §5 onward was written into `HYPOTHESES.md`, with its
pass/fail rule, and committed before it ran. The commit history is the
timestamp. Two rule changes made after inspecting data, but before the
affected test ran, are documented in §6.2. Both made the rule stricter.

## 3. The correction

### 3.1 The bug

Engine v1 reserved the account's cash at the start of each bar, before
that bar's exits settled, and never credited sell proceeds back to the
batch. On a rebalance day, new entries could use only cash that was
already idle. Exit proceeds then sat in cash for a month or a quarter.
When the buys exceeded cash, alphabetically later tickers were starved.

The published US walk-forward book averaged **67% invested**, falling to
58% on bearish days. A book that is one-third cash lags in bull markets
and cushions in bear markets by construction. Using only the published
returns, a constant 67% buy & hold / 33% cash portfolio reproduces 93% of
the published US interaction.

### 3.2 The fix

Engine v2 is opt-in. It credits exit and trim proceeds, at a 2% haircut,
before capping buys, and scales unaffordable buys down pro rata. It
settles sells first and trims any buy the account can't afford at its
actual fill, so cash never goes negative.

A regression test reproduces 5,878 rows written by the engine *before*
v2 existed, bit for bit. Every published configuration was rerun under v1
and v2 on one data snapshot:

- buy & hold matched the stored returns with correlation 1.0000 and a
  cumulative-return gap of at most 0.2 pp;
- the v1 rerun reproduced every published number.

### 3.3 Verdict under the rule written before the rerun

| US regime interaction | Bull − bear gap / day | 95% CI | Retained | 2022 momentum max DD | Verdict |
|---|---|---|---|---|---|
| Published (v1) | −0.122% | [−0.244, −0.011] | — | −18.24% | — |
| v2 (bug fixed) | −0.015% | [−0.132, +0.082] | 0.12 | −18.67% | **Does not survive** |
| v2full (also scaled up to 100%) | −0.015% | [−0.132, +0.082] | 0.12 | −18.67% | **Does not survive** |

Invested fraction rose from 0.67 to 0.98, and beta to buy & hold from
0.67 to 0.87.

A "fully invested" variant first came out *less* invested than v2,
because its scaling also pushed over-100% books down. After that was
fixed, it is identical to v2 in the US (`results/v2full_fix/`).

## 4. Results under engine v2 (fixed universes)

### 4.1 US 2015–2024 (96-combination walk-forward)

| | Total return | CAGR | Sharpe | Calmar | Max DD | Max-DD duration |
|---|---|---|---|---|---|---|
| Momentum, in-sample | +1,559% | 32.5% | 1.14 | 1.00 | −32.4% | 112 days |
| Momentum, walk-forward | +420% | 31.7% | 1.13 | 0.87 | −36.6% | 124 days |
| Buy & hold | +1,255% | 29.9% | 1.19 | 0.72 | −41.4% | 571 days |

Figure: `tearsheet_v2.png`. Walk-forward momentum still trails buy & hold
on total return and Sharpe. Its recovery after the COVID crash took 124
days, not the 378 originally reported. Most of the original 378 was idle
cash.

### 4.2 Three universes, 2009–2024 out of sample (12-combination walk-forward)

| Universe | Momentum CAGR | Sharpe | Max DD | B&H CAGR | Sharpe | Max DD | Interaction / day | 95% CI |
|---|---|---|---|---|---|---|---|---|
| US | 27.2% | 1.06 | −35.9% | 29.7% | 1.19 | −45.9% | −0.015% | [−0.132, +0.082] |
| Europe | 10.8% | 0.61 | −35.6% | 12.8% | 0.78 | −31.3% | **+0.070%** | **[+0.003, +0.136]** |
| Emerging | 7.1% | 0.38 | −51.9% | 12.6% | 0.60 | −41.6% | +0.023% | [−0.099, +0.141] |

Momentum never beats buy & hold on Sharpe. The only significant
interaction is Europe's, and it is positive: momentum does relatively
worse in European bear markets.

## 5. Where the 2022 protection came from

### 5.1 Sector attribution (H3)

The published attribution counted names momentum *selected*. Under v1
many of them were never bought. A replay of the stored walk-forwards
reproduces every stored equity curve to about 3e-16, and reproduces 7 of
8 published sector shares exactly when counting selections. Counting
actual v2 holdings on the 33 bearish-day rebalances:

- US momentum holds tech (73%) and consumer cyclicals (82%) far more
  often than Europe (21%, 27%).
- Europe holds healthcare more often (91% vs 58%).
- The energy ordering reverses, and so does the "Europe is more
  concentrated" argument (31% vs 38% of folds pick the 10% fraction).

**Verdict: partly holds (3 of 4 orderings).** The tilts are real, but the
US protective effect they were meant to explain is gone (§3).

### 5.2 Five US bear episodes (H4)

Fixed-parameter momentum v2 (in-sample modal parameters, so 2008 is
covered) against equal-weight buy & hold of the same 37 names. Windows
run from S&P 500 peak to trough:

| Episode | Momentum | B&H | Excess (pp) | Allocation | of which energy | Selection |
|---|---|---|---|---|---|---|
| GFC 2007–09 | −31.9% | −40.2% | +8.4 | +7.7 | −1.0 | +13.3 |
| 2011 | −34.6% | −16.8% | −17.8 | −6.3 | +0.1 | −15.5 |
| Q4 2018 | −26.9% | −26.8% | −0.1 | −1.7 | −0.1 | +1.0 |
| COVID 2020 | −33.5% | −27.1% | −6.4 | −5.2 | +0.2 | −2.6 |
| **2022** | **−7.3%** | **−42.4%** | **+35.1** | **+48.0** | **+26.5** | **−0.9** |

The attribution columns are daily Brinson terms summed over the episode.

- **H4a passes, energy-driven.** Allocation is 99.8% of 2022's arithmetic
  excess, and energy is 55% of that. Momentum held 42% energy against
  0.7% for the benchmark.
- **H4b: 2022 is the exception.** Momentum beat buy & hold in 1 of the
  other 4 episodes. Across all 12 grid parameter sets, 10 give
  "exception" and 2 "mixed"; none gives "rule". The walk-forward series
  agrees for the post-2009 episodes.

Momentum protects when last year's winners are defensive (energy and
healthcare in 2022). It gets hurt when they are the next crash's
epicentre (87% tech going into COVID).

## 6. Survivorship: a point-in-time S&P 500

### 6.1 Data

Daily S&P 500 membership comes from fja05680/sp500 (commit `a2430f2`).
943 tickers were members in 2005–2024. Prices are from Yahoo, the only
free source reachable here, and Yahoo keeps only still-listed symbols.

- **Coverage:** 74.3% of member-days, rising from 53% in 2005 to 96% in
  2024. That gradient is survivorship itself.
- **Missing:** 351 names have no prices at all. Seventeen of them were
  still members at the end of 2024 and have since been acquired or
  renamed.
- **Excluded:** five reused tickers whose Yahoo series belongs to a
  later company.

### 6.2 Rename map (H1)

Twenty renamed tickers were mapped to their current symbol, each with
two pieces of documented evidence:

- the SEC EDGAR record now trading under the new ticker lists the old
  company's name;
- the new ticker's prices cover 100% of the old ticker's member-days.

Coverage rose to **76.7%**.

Two rule changes were made after inspecting candidates and before the
test ran. Both are stricter:

1. A "name changed at the swap date" criterion was dropped as
   sufficient. It accepted acquisitions where the acquirer renamed
   itself, such as SunTrust → Truist.
2. Substring name matching was replaced by a strict token rule.

### 6.3 Results

| 2009–2024 | Momentum CAGR | Sharpe | Max DD | Benchmark CAGR | Sharpe | Max DD | Interaction / day | 95% CI |
|---|---|---|---|---|---|---|---|---|
| Fixed 37 names | 27.2% | 1.06 | −35.9% | 29.7% (B&H) | 1.19 | −45.9% | −0.015% | [−0.132, +0.082] |
| PIT S&P 500, renamed (H1a) | **14.0%** | 0.72 | −35.3% | **14.0%** (PIT EW) | 0.81 | −36.1% | **+0.075%** | **[+0.003, +0.152]** |
| PIT, 40 most liquid members | 22.5% | 0.88 | −38.6% | 14.0% | 0.81 | −36.1% | +0.156% | [+0.039, +0.271] |

**H1a passes, narrowly.** On the point-in-time universe momentum does
significantly *worse* than its benchmark in bear markets relative to bull
markets. That is the textbook momentum-crash pattern, the same direction
as Europe, and the opposite of the original claim.

The liquid-40 control shows that a narrow, large-cap, point-in-time
universe still earns far more than the broad one. So the fixed list's
inflation comes from both survivorship and concentration in today's
mega-caps.

### 6.4 Extending to 2000 (H8)

{{H8}}

## 7. Factor regressions (H5)

French data library factors, Newey-West errors. US and Europe are daily;
Emerging is monthly.

| Series | α / yr | t | MKT | UMD | t(UMD) | Active return vs UMD, monthly corr. |
|---|---|---|---|---|---|---|
| US momentum v1 | +3.8% | 1.2 | 0.94 | 0.45 | 17.0 | 0.36 |
| US momentum v2 | +10.2% | 2.9 | 1.15 | 0.54 | 21.9 | 0.31 |
| US buy & hold, 37 names | **+11.8%** | **4.4** | 1.12 | 0.10 | 6.3 | — |
| US PIT momentum (renamed) | −0.3% | −0.2 | 1.08 | 0.46 | 29.7 | **0.71** |
| US PIT equal-weight benchmark | +0.7% | 0.9 | 0.92 | −0.10 | −13.0 | — |
| Europe momentum v2 | +2.2% | 0.8 | 0.78 | 0.58 | 17.7 | 0.33 |
| Emerging momentum v2 (monthly) | −2.7% | −0.4 | 1.14 | 0.70 | 4.8 | 0.25 |

- **H5a passes.** The UMD loading is positive with t > 2, both on the
  fixed list and point-in-time.
- **H5d passes.** v2 has a higher market beta than v1 in all three
  universes.
- **The engine builds real momentum.** On the broad point-in-time
  universe its active return tracks UMD at 0.71.
- **Alpha belongs to the universe, not the strategy.** The fixed list's
  10% momentum alpha is the list's: buy & hold of the same names has
  11.8%. v1's active alpha against buy & hold was about −8% a year (the
  bug), and v2's is about −1.6% (n.s.).

## 8. A second strategy: short-term reversal

Long the bottom fraction by trailing 5/10/21-day return, on the same
engine, folds, regimes and costs. 24 pre-registered tests, Holm-adjusted.

| 2009–2024 CAGR / Sharpe | Reversal | Momentum | Buy & hold |
|---|---|---|---|
| US | 17.6% / 0.82 | 27.2% / 1.06 | 29.7% / 1.19 |
| Europe | 12.6% / 0.66 | 10.8% / 0.61 | 12.8% / 0.78 |
| Emerging | 7.6% / 0.40 | 7.1% / 0.38 | 12.6% / 0.60 |

- **None of the 24 tests survives Holm adjustment.** 3 are significant
  before correction, roughly what chance produces.
- **The point estimates have a consistent sign.** In all three markets,
  reversal beats momentum in high-volatility bear markets and lags it in
  bull markets. That is the expected crash-insurance pattern, but the
  tests can't distinguish it from noise.
- **Nagel's (2012) prediction finds no support.** Reversal's edge over
  buy & hold is not detectably larger in high-volatility regimes.
- **Costs are higher.** Reversal pays 0.75–2.3% a year against 0.24–0.67%
  for momentum.

## 9. Momentum crashes and volatility scaling (H6)

Following Barroso & Santa-Clara (2015), as a long-only analogue: the
book's gross exposure is min(20% / σ̂, 1), where σ̂ is the six-month
realised volatility of the selected names. The rest is held in cash.
Because engine v2's cash cap would otherwise undo any per-name scaling,
the scale is applied to the whole book. The baseline is the same
strategy held fully invested.

| US fixed universe, walk-forward | CAGR | Sharpe | Max DD | Worst month | 2009 rebound max DD | COVID window return | COVID max DD |
|---|---|---|---|---|---|---|---|
| Baseline (fully invested) | 25.5% | 1.05 | −30.9% | −15.1% | −18.3% | +4.0% | −30.2% |
| Vol-scaled, 20% target | 19.8% | 1.01 | −29.0% | −14.2% | **−4.3%** | −8.8% | **−25.5%** |
| Vol-scaled, 15% | 15.5% | 1.00 | −24.2% | −10.6% | −3.3% | −6.7% | −19.7% |
| Vol-scaled, 25% | 21.7% | 0.99 | −30.9% | −15.1% | −7.0% | −9.7% | −30.2% |

- **H6a passes on the US fixed universe.** Within-window drawdowns are
  shallower in both crash windows.
- **H6b fails to find a Sharpe gain.** The difference is −0.03, CI
  [−0.20, +0.11].

The long-only version cuts drawdowns, but, unlike the long-short factor
in the literature, it does not improve risk-adjusted return. In COVID it
de-risked after the crash and missed the rebound. {{H6PIT}}

## 10. Robustness (H7)

- **Max-drawdown bootstrap (H7c).** Momentum's lower max drawdown is not
  reliable. In a paired block bootstrap, P(momentum's max DD is
  shallower) is 0.43–0.55 across both US samples and both block lengths
  (20 and 60 days). Every 95% CI of the difference spans zero.
- **Parameter sweep (H7a, pass).** The published "only 1 of 96 parameter
  sets beats buy & hold" (US 2015–2024, in-sample) reproduces exactly
  under v1. Under v2, **40 of 96** sets beat buy & hold, and the median
  total return rises from +301% to +1,123%. The bug handicapped every
  parameter set. These are in-sample results, and the walk-forward still
  doesn't beat buy & hold.
- **Transaction costs (H7b, robust null).** The walk-forward was rerun
  with a flat one-way cost of 0–50 bp, applied during parameter selection
  too. The bull/bear interaction is insignificant at every level. Each
  10 bp costs momentum about 1–1.5 CAGR points. Momentum trails buy &
  hold even at zero cost (−2.0 points), so there is no break-even.

## 11. Limitations

- **Survivorship is reduced, not removed.** 23% of point-in-time
  member-days still lack prices, mostly failures and cash takeovers.
  Europe and Emerging stay on fixed present-day lists.
- **Concentration.** Fixed-universe books hold 4–8 names, which adds
  idiosyncratic noise. The point-in-time book holds about 40–100.
- **No FX layer.** European local listings are in local currency.
- **One regime reference.** SPY regimes are used for all three markets.
- **Sectors** are today's Yahoo classification.
- **In-sample choices** in the bear-episode study use the modal
  walk-forward parameters. A 12-set robustness check guards against
  them.
- **Long-only throughout.** Factor results are about loadings. The
  books are not factor portfolios.
- **Nothing here is an allocation rule.**

## 12. Conclusion

The headline of the first version, "momentum's drawdown protection is a
US phenomenon", came from an idle-cash bug in the backtester. With the
bug fixed, and on a point-in-time universe, the evidence points the other
way. US momentum does modestly but significantly worse relative to its
benchmark in bear markets, as in Europe. The one large protective
episode, 2022, was an energy and healthcare sector bet that does not
recur across five US bear markets.

The engine itself holds up. It reproduces the published numbers exactly
under v1, its replays match stored curves to machine precision, and its
point-in-time momentum tracks the academic UMD factor at 0.71.

## Reproducibility

Every number traces to a script and an output folder:

| Section | Script | Output |
|---|---|---|
| §3 | `run_cash_v2.py`, `run_v2full_fix.py` | `results/v2/`, `results/v2full_fix/` |
| §4 | (same) | `tearsheet_v2.png` (`run_tearsheet_v2.py`) |
| §5 | `run_sector_attribution.py`, `run_bear_episodes.py` | `results/sector_v2/`, `results/bear_episodes/` |
| §6 | `build_universe_us.py`, `build_rename_map.py`, `run_regimes_pit.py`, `run_pit_renamed.py`, `run_pit_2000.py` | `results/pit_us*/` |
| §7 | `run_factor_regressions.py` | `results/factors/` |
| §8 | `run_regimes_reversal.py` | `results/reversal/` |
| §9 | `run_volscaled.py` | `results/volscaled/` |
| §10 | `run_robustness_v2.py` | `results/robustness_v2/` |

Pre-registrations are in `HYPOTHESES.md`. The test suite is
`pytest test_*.py` (synthetic data and committed files only; 92% line
coverage of `quantbt`; run in CI). An interactive explorer of the v2
results is in `web/`.

## References

Barroso, P. and Santa-Clara, P. (2015). Momentum has its moments. *Journal of Financial Economics*, 116(1), 111–120.

Brinson, G. P., Hood, L. R. and Beebower, G. L. (1986). Determinants of portfolio performance. *Financial Analysts Journal*, 42(4), 39–44.

Daniel, K. and Moskowitz, T. J. (2016). Momentum crashes. *Journal of Financial Economics*, 122(2), 221–247.

Fama, E. F. and French, K. R. (2015). A five-factor asset pricing model. *Journal of Financial Economics*, 116(1), 1–22.

Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 6(2), 65–70.

Jegadeesh, N. and Titman, S. (1993). Returns to buying winners and selling losers. *Journal of Finance*, 48(1), 65–91.

Künsch, H. R. (1989). The jackknife and the bootstrap for general stationary observations. *Annals of Statistics*, 17(3), 1217–1241.

Nagel, S. (2012). Evaporating liquidity. *Review of Financial Studies*, 25(7), 2005–2039.

Newey, W. K. and West, K. D. (1987). A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. *Econometrica*, 55(3), 703–708.

Shumway, T. (1997). The delisting bias in CRSP data. *Journal of Finance*, 52(1), 327–340.
