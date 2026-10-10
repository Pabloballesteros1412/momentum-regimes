# Hypotheses and pass/fail rules

Every statistical test run from 2026-10-11 onward is written down here,
with its pass/fail rule, **and committed before the test is run**. The
commit history is the timestamp. Anything decided after seeing a result is
labelled **exploratory** in the results documents.

Common conventions, unless an entry says otherwise:

- Daily returns. Common out-of-sample window 2009-01-05 to 2024-12-30.
  Engine v2.
- SPY regime labels from `results/v2/spy_regime_rerun.csv` (trend: SPY vs
  its 200-day MA; vol: 21-day realised vol vs its expanding 75th
  percentile).
- Moving block bootstrap, 20-day blocks, 5,000 iterations, seed 0, 95%
  two-sided percentile CI.
- "Interaction" means mean daily (strategy − benchmark) on bullish days
  minus the same on bearish days.

Earlier pre-registrations that this file doesn't repeat:
`results/v2/FINDINGS_CASH.md` (decision rule) and
`run_regimes_reversal.py` (the 24-test reversal family).

---

## H1 — Task 1: point-in-time S&P 500 with a verified rename map

**Context.** On the PIT S&P 500 with 74.3% member-day coverage
(`results/pit_us`), the momentum − benchmark interaction was +0.081%/day
[+0.009, +0.156]. That is the opposite sign to "drawdown protection", and
it was labelled exploratory. Task 1 raises coverage by mapping renamed
tickers, using only mappings with evidence. This entry turns the earlier
exploratory finding into a confirmatory test on the improved-coverage
data.

**Mapping rule (fixed before any mapping is made).** An old ticker T is
mapped to a current ticker T' only if all of these hold:

1. **Same legal entity.** On SEC EDGAR, the company record (CIK) whose
   current ticker is T' lists the old company's name as its current or a
   former name.
2. **Continuous prices.** T''s Yahoo series has a bar on at least 99% of
   T's member-days, and its first bar is on or before T's first member-day
   in 2005–2024.
3. **No double counting.** T's membership intervals don't overlap T''s
   own membership intervals.

The old company's name comes from Wikipedia's S&P 500 change tables, or,
failing that, from a hand-written candidate list. Each name is still
verified on EDGAR.

**H1a (primary, confirmatory).** On the renamed-map PIT universe, momentum
v2's interaction against the PIT equal-weight benchmark is **positive**:
momentum does relatively worse in bear markets.

- *Pass:* 95% CI excludes 0 and the estimate is > 0.
- *Fail:* CI includes 0, or the estimate is ≤ 0.

**H1b (descriptive, no test).** Report member-day coverage before and
after, the number of mappings accepted and rejected (with reasons), and
the change in momentum and benchmark CAGR, Sharpe and max DD.

**Fixed settings.** The same 12-combination grid, 16 folds and warm-up as
`results/pit_us`. No delisting return (none can trigger on Yahoo data).
Output goes to `results/pit_us_renamed/`. `results/pit_us/` is not
touched.

---

## H3 — Task 3: sector attribution under engine v2 (descriptive)

**Published claim (README §3, engine v1).** Across the bearish-day monthly
rebalances in 2009–2024, US momentum held consumer cyclicals more often
than Europe (72.7% vs 30.3%) and technology more often (57.6% vs 18.2%).
Europe held healthcare more often (81.8% vs 54.5%) and energy more often
(42.4% vs 27.3%). Europe picked the concentrated 10% fraction more often
(62.5% vs 50% of folds).

**Method.** Replay each walk-forward's trading folds with its stored
parameters (`quantbt/validation/replay.py`). The replayed out-of-sample
equity must equal the stored curve to a relative 1e-9, or the universe is
dropped and the failure reported. Holdings are the positions after each
rebalance settles. Sectors are Yahoo Finance's `sector` field, as a
snapshot taken today; the snapshot date is recorded. The metric is the
same as the published one: the share of bearish-day rebalances (SPY trend
label on the rebalance day) whose portfolio holds at least one name in the
sector. Value weights are reported as well.

**Method check (run first).** The v1 replay should reproduce the published
v1 shares. If it doesn't, the difference is reported and the v1 *replay*
numbers, not the published ones, are the baseline for the v2 comparison.

**H3 (descriptive, no significance test).** The composition story "still
holds under v2" if **all four** published orderings hold in the v2 replay:

- US > Europe on consumer cyclical share.
- US > Europe on technology share.
- Europe > US on healthcare share.
- Europe > US on energy share.

It "partly holds" if 2 or 3 orderings hold, and "does not hold" if 0 or 1
do. The concentration claim is checked separately (share of folds choosing
the 10% fraction, Europe > US).

---

## H4 — Task 4: is 2022 explained by sector composition, and is it the rule?

**Episodes, fixed before any computation.** S&P 500 closing peak to
trough:

| Episode | Start (peak) | End (trough) |
|---|---|---|
| GFC | 2007-10-09 | 2009-03-09 |
| 2011 | 2011-04-29 | 2011-10-03 |
| Q4 2018 | 2018-09-20 | 2018-12-24 |
| COVID | 2020-02-19 | 2020-03-23 |
| 2022 | 2022-01-03 | 2022-10-12 |

**Series.**

- **Primary:** momentum v2 with **fixed parameters** over 2005–2024 on the
  37-name US universe, against equal-weight buy & hold of the same names
  (engine v2). The walk-forward only trades from 2009, so it can't cover
  the GFC. The fixed parameters are the modal v2 US walk-forward choice
  (from `regime_US_wf_momentum_v2_folds.csv`). That is an in-sample choice
  and is labelled as such. Robustness: the same episode returns for all 12
  grid parameter sets.
- **Secondary:** the v2 walk-forward replay, for the four episodes after
  2009.

**Attribution.** Daily Brinson decomposition of momentum − B&H, using GICS
sectors from Yahoo (`data/sectors_yahoo.csv`) and summed arithmetically
over the episode:

- *Allocation* = Σ (w_mom,s − w_bh,s) × (r_bh,s − r_bh)
- *Selection* = Σ w_mom,s × (r_mom,s − r_bh,s)
- *Cash* = w_mom,cash × (0 − r_bh)

The residual (compounding, costs) is reported. The *energy* allocation
term is reported separately.

**H4a (2022 explained by composition).** The pass rule:

- **Passes** if 2022's allocation effect is positive and accounts for
  ≥ 50% of 2022's arithmetic excess return.
- **"Energy-driven"** if, in addition, the energy allocation term alone
  is ≥ 50% of the allocation effect.

**H4b (rule or exception).** Count the other four episodes in which
primary-series momentum beat buy & hold (episode excess return > 0):

- 3–4 of 4: 2022 is **the rule**.
- 2: **mixed**.
- 0–1: 2022 is **the exception**.

This rule also applies across the 12 parameter sets, by majority.

No significance test. Five episodes can't support one, and none is
claimed.

---

## H5 — Task 5: Fama-French 5 factors + momentum (UMD)

**Data.** Kenneth French's data library, downloaded 2026-10-11 (copies in
`data/ff/`):

- **US:** 5 factors (2×3) daily and the momentum factor daily.
- **Europe:** 5 factors daily and the momentum factor daily (USD).
- **Emerging:** 5 factors monthly and the momentum factor monthly (no
  daily file exists).

**Model.** r − RF = α + b·MKT + s·SMB + h·HML + r·RMW + c·CMA + u·UMD + e.
OLS with Newey-West (HAC) standard errors: 10 lags for daily data, 3 for
monthly. US series use US factors, Europe uses Europe factors, Emerging
uses Emerging factors (monthly). The sample is each series' own
out-of-sample days within 2009–2024.

**Series.** Walk-forward momentum v1 and v2 and buy & hold v2 for each
universe (`results/v2/curves`); PIT S&P 500 momentum and its benchmark
(`results/pit_us`, and `results/pit_us_renamed` if finished); and the
active series momentum − benchmark.

**H5a (the engine reproduces the academic factor).**

- **Pass** if US walk-forward momentum v2 on the fixed universe has a
  positive UMD loading with HAC t > 2.
- **H5a-PIT:** the same rule for PIT S&P 500 momentum (renamed map if
  available, else `pit_us`).

**H5b (tracking, descriptive threshold).** Monthly correlation between
(momentum − benchmark) and UMD:

- ≥ 0.5 "tracks UMD well".
- 0.3–0.5 "tracks partly".
- < 0.3 "does not track".

Reported for every universe and version.

**H5c (alpha).** Report α with its HAC t-stat. α is significant if
|t| > 2. No direction is predicted.

**H5d (v1 vs v2, directional prediction).** The v2 market loading exceeds
v1's in every universe, because idle cash lowers beta. Pass if true in all
three.

---

## H6 — Task 6: volatility-scaled momentum and momentum crashes

**Strategy** (`quantbt/strategies/volscaled.py`). Same selection as
momentum. Book gross = min(target_vol / σ̂, 1), where σ̂ is the annualised
126-day volatility of an equal-weight portfolio of the selected names,
using past closes only. The rest is cash, with no leverage. Engine v2,
`GrossTargetSizer`.

**Variants.** All are walk-forwards on the 12-combination momentum grid
over 2005–2024, with the same folds and warm-up as the regime study. The
volatility settings are fixed, not tuned.

- **Baseline (like-for-like):** target_vol = 10.0. The scale is always 1,
  so the book is fully invested.
- **Scaled (primary):** target_vol = 0.20. Sensitivity runs at 0.15 and
  0.25.
- **Plain momentum v2** (`results/v2`) is reported for reference.

**Universes.** US fixed 37 names (primary). The PIT S&P 500 with the
renamed map (`results/pit_us_renamed` membership) runs the baseline and
0.20 if time allows.

**Crash windows** (Daniel & Moskowitz rebounds):

| Window | Dates |
|---|---|
| 2009 rebound | 2009-03-09 → 2009-06-30 |
| COVID | 2020-02-19 → 2020-06-30 |

**H6a (primary).** Scaled 0.20 has a *shallower max drawdown within each
crash window* than the baseline.

- **Pass:** true in both windows on the US fixed universe.
- **H6a-PIT:** the same rule on the PIT universe, if run.

**H6b.** Full-sample (2009–2024 out of sample) Sharpe difference, scaled
0.20 minus baseline. Paired moving block bootstrap of the daily return
pairs (20-day blocks, 5,000 iterations, seed 0), 95% CI.

- Significant if the CI excludes 0. Barroso & Santa-Clara predict > 0.

**H6c (descriptive).** Full-sample max drawdown, worst month and skewness
for every variant, and window returns. No test.
