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
