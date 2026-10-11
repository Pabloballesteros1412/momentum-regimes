# How much of momentum's drawdown protection survives once it is fully invested?

**Short answer, from the reruns (`python run_cash_v2.py`, 2026-10-10):**
in the US, the published drawdown protection **does not survive** fixing
the idle-exit-cash bug (v2). It is **weakened** when the book is made fully
invested (v2full). Under both, the US regime interaction keeps its sign but
its 95% CI now includes zero. Momentum still beats buy & hold on drawdown in
the 2022 window under both versions, so the 2022 condition of the rule holds.
That doesn't rescue v2, which fails on the retained share.

| US regime interaction (bull − bear, mean daily) | Gap | 95% CI | Retained vs v1 rerun | 2022 max DD, momentum vs B&H (−40.15%) | Verdict |
|---|---|---|---|---|---|
| v1 rerun (= published) | −0.122% | [−0.244, −0.011] | — | −18.24% | (baseline) |
| **v2** (bug fixed, design cash kept) | −0.015% | [−0.132, +0.082] | **0.12** | −18.67% ✅ | **Does not survive** (retained < 1/3) |
| **v2full** (fully invested) | −0.060% | [−0.171, +0.041] | **0.49** | −19.96% ✅ | **Weakened** (CI includes 0; retained between 1/3 and 2/3) |

Section 3 of the earlier analysis expected the reverse ordering: v2full not
surviving, and v2 depending on how much of the 0.67 β was idle cash. The
reruns put most of it down to idle cash. Fixing only the bug lifts the US
walk-forward book's average invested fraction from 0.67 to 0.98 and removes
88% of the interaction. See "Results of the reruns" for details and for the
v2full oddity behind the ordering.

---

## Status

| Step | State |
|---|---|
| 1. Invested fraction on real data | **Done.** `invested_fraction.csv` |
| 2. Engine v2, opt-in, with an exact default-path test | **Done.** `python test_engine_v2.py` (re-run 2026-10-10: passes) |
| 3. v2 rerun vs published | **Done.** Drift check passed and the v1 rerun reproduces the published numbers (below). |
| 4. This document | Verdicts below, under the pre-registered rule. |
| 5. README sentences | Listed below. README untouched. |

**Data snapshot.** Yahoo Finance was reachable on 2026-10-10. `run_cash_v2.py`
also needs `pyarrow` for its price cache, which `requirements.txt` doesn't
list.

---

## What is established

### 1. The default engine path is unchanged

The engine at commit `1b2ba42`, before any v2 code existed, was used to
write `tests/fixtures/v1_golden.csv`. It covers four synthetic scenarios:
buy & hold, vol-target momentum, equal-weight quarterly momentum, and a
walk-forward with `SignalCache`. Today's engine with default arguments
reproduces all 5,878 rows **exactly** (cash, holdings and equity compared
with `!=` on doubles). Any future leak into the published path fails
`test_engine_v2.py`.

### 2. What v2 changes

Two options on the sizer, both off by default
(`quantbt/risk/sizing.py`, `quantbt/engine/backtest.py`):

- **`engine_version="v2"`**: sells and trims are credited to the bar's
  batch, at a 2% haircut, before buys are capped. Buys that still exceed
  cash are scaled down pro rata, instead of starving the alphabetically
  later names. The batch settles sells first, and a buy the account can't
  afford at its actual fill is trimmed, so cash never goes negative (tested).
  Orders still fill at the next bar's open (tested).
- **`full_investment=True`** (requires v2): rescales long targets to 100%
  gross, keeping their relative vol-target weights. This removes the cash
  that vol targeting holds *by design* when the selected names' weights sum
  to under 100%. With `max_weight=0.35`, a 4-name top decile can't exceed
  140%. In high-volatility markets it can drop well under 100%, which is
  intentional de-risking, not the bug.

`run_cash_v2.py` reports three momentum books:

- **v1:** the published engine.
- **v2:** the bug fixed, design cash kept. This answers "do the published
  conclusions survive the fix".
- **v2full:** literally fully invested. This answers your question as
  worded.

On synthetic data (engine verification only, *not evidence about the
paper*), v2 lifted a vol-target momentum book's average invested fraction
from 0.745 to 0.985, and its minimum from 0.30 to 0.96. Buy & hold was
unchanged at 0.982.

### 3. The published US protection behaves like lower exposure

`run_beta_diagnostic.py` uses only the published `regime_returns_detail.csv`,
over the 4,024 days both strategies have returns. Output:
`results/v2/beta_diagnostic.csv`.

| Universe | β (mom on B&H) | β bull / bear | Published interaction (bull − bear) | Constant-β exposure alone | Share explained | Residual after β | Residual 95% CI |
|---|---|---|---|---|---|---|---|
| US | 0.668 | 0.695 / 0.631 | −0.122% [−0.244, −0.011] | −0.114% | **93%** | −0.009% | [−0.103, +0.070], n.s. |
| Europe | 0.840 | 0.889 / 0.774 | +0.077% [+0.001, +0.159] | −0.023% | −30% | +0.100% | [+0.027, +0.177], **sig.** |
| Emerging | 0.561 | 0.696 / 0.383 | −0.035% [−0.173, +0.100] | −0.039% | 112% | +0.004% | [−0.111, +0.109], n.s. |

All values are mean daily return differences.

How to read it:

- **US.** Any book running at about two-thirds equity exposure, whatever the
  reason, lags in bull markets and cushions in bear markets by almost exactly
  the published amount. Momentum's conditional beta does drop a little in
  bear markets (0.70 to 0.63), but the leftover interaction is small and not
  significant. **The headline US finding is not evidence that momentum picks
  stocks that protect. It's consistent with momentum holding less equity.**
- **Europe.** The published "opposite direction" result gets *stronger* after
  removing exposure: the residual is +0.100%/day and clearly significant. In
  Europe, momentum's stock selection does worse in bear markets than its
  exposure would predict.
- **Emerging.** Nothing before, nothing after.

Caveats:

- β is estimated over the full sample (hindsight). It's a diagnostic, not a
  tradable hedge.
- A single β doesn't separate the three sources of low exposure: idle exit
  cash (the bug), vol-target cash (design), and the picks' own betas. That
  split is what step 3 measures.

### 4. Why idle cash would produce exactly this pattern

Under v1, exit proceeds wait for the next monthly rebalance. That cash is
uncorrelated with the market, so it lowers beta in every regime. Lower beta
alone makes momentum − B&H negative when B&H rises and positive when it
falls, which is the published US sign pattern. The same mechanism also
offers an alternative reading of the COVID narrative in README §2: a book
partly in cash after the March 2020 rebalances would also "miss the
rebound". Both are hypotheses until the rerun separates them.

---

## Decision rule, written before the reruns

The reruns compare v2 and v2full against the **v1 rerun** (same data
snapshot), not against the published CSVs, so data drift can't pass for an
effect. `run_cash_v2.py` writes the drift check first
(`drift_check.csv`: correlation ≥ 0.999 and a cumulative-return gap of
≤ 2 pp against the stored buy & hold returns, plus SPY regime label
agreement).

For the US regime interaction, let *retained* = v2 gap ÷ v1-rerun gap
(`summary.json`).

| Verdict | Condition |
|---|---|
| **Survives** | Same sign, 95% CI still excludes 0, retained ≥ 2/3 |
| **Weakened** | Same sign, but the CI includes 0 or retained is between 1/3 and 2/3 |
| **Does not survive** | Retained < 1/3, or the sign flips |

The 2022 stress window also has to hold: v2 momentum's max drawdown must
stay shallower than buy & hold's (−40.15% published). COVID is reported but
was already a case where momentum did worse.

Europe and Emerging: the published conclusion is "does not replicate". It
changes only if Emerging becomes significant in the US direction, or Europe
loses or flips its significance.

Verdicts are reported separately for v2 (bug only) and v2full (fully
invested).

**Expectation given section 3, to be confirmed or refuted:** v2full will
probably not survive in the US, because it removes the low exposure that
explains 93% of the effect. Whether v2 survives depends on how much of the
0.67 β is idle cash. Section 3 can't tell.

---

## Results of the reruns

All files are in `results/v2/`. Curves and walk-forward fold choices are in
`curves/`.

### Drift check (`drift_check.csv`): passed

| Series | Days | Correlation | Cumulative return, stored → rerun | Within tolerance |
|---|---|---|---|---|
| US buy & hold | 5,032 | 1.0000 | 79.487 → 79.491 | ✅ |
| Europe buy & hold | 5,171 | 1.0000 | 6.6717 → 6.6722 | ✅ |
| Emerging buy & hold | 5,032 | 1.0000 | 8.6744 → 8.6725 | ✅ |
| SPY regime labels | 4,760 | 100% agreement | | ✅ |

No day differs by more than 1 bp. The v1 rerun also reproduces the
published momentum results: the walk-forward total return is +178.33%
(published +178.27%), max drawdown −35.58%, Calmar 0.52 and recovery 378
days, all the same as published. The regime interactions match to the
fourth decimal, and v1-rerun vs published momentum returns correlate at
1.0000 in all three universes. So every v1 → v2 difference below comes from
the engine, not from data drift.

### Invested fraction (`invested_fraction.csv`)

| Book | v1 mean | v2 mean | v2full mean | v1 share of days < 90% | v2 share of days < 90% |
|---|---|---|---|---|---|
| US 2015–24 walk-forward | 0.669 | 0.979 | 0.966 | 66% | 0% |
| US 2015–24 in-sample | 0.706 | 0.885 | 0.875 | 56% | 13% |
| US 2005–24 walk-forward | 0.816 | 0.986 | 0.971 | 46% | 0% |
| Europe 2005–24 walk-forward | 0.761 | 0.973 | 0.968 | 52% | 4% |
| Emerging 2005–24 walk-forward | 0.758 | 0.976 | 0.971 | 59% | 5% |
| Buy & hold (any) | 0.97–0.99 | same | n/a | | |

Under v1, the US book's invested fraction falls to 0.58 on bearish days,
against 0.69 on bullish days. That is the idle-cash mechanism of section 4,
seen directly in the holdings.

**v2full oddity.** v2full is meant to be "literally fully invested", yet its
mean invested fraction is slightly *below* v2's in every book. Its US
2015–24 walk-forward total return (+212%) is also far below v2's (+420%).
Rescaling every target to 100% gross probably leaves no cash buffer for the
2% haircut and next-open fills, so buys get trimmed, and the walk-forward
then picks different parameters. That explains why v2full keeps *more* of
the interaction than v2. Treat the v2full row as "approximately fully
invested". I did not investigate this further.

### US 2015–2024 headline metrics (`headline_metrics_us2015.csv`)

| Strategy | Version | Total return | Sharpe | Calmar | Max DD | Max DD days |
|---|---|---|---|---|---|---|
| Walk-forward momentum | v1 rerun | +178.3% | 0.90 | 0.52 | −35.58% | 378 |
| | v2 | +419.9% | 1.13 | 0.87 | −36.58% | 124 |
| | v2full | +212.4% | 0.90 | 0.67 | −31.23% | 133 |
| In-sample momentum | v1 rerun | +523.8% | 0.92 | 0.88 | −22.86% | 1,050 |
| | v2 | +1,559.2% | 1.14 | 1.00 | −32.41% | 112 |
| Buy & hold | v1 = v2 | +1,254.8% | 1.19 | 0.72 | −41.35% | 571 |

Fixing the bug doesn't make walk-forward momentum beat buy & hold
out of sample. It does make its max drawdown about as deep as before rather
than shallower, and the recovery times change completely.

### Stress windows, US walk-forward (`stress_us2015.csv`)

| Window | Version | Momentum return | Momentum max DD | Days to recover | B&H max DD |
|---|---|---|---|---|---|
| COVID crash | v1 | −18.20% | −35.58% | 378 | −30.27% |
| | v2 | −17.54% | −36.58% | 124 | |
| | v2full | −14.53% | −31.23% | 133 | |
| 2022 bear | v1 | −4.81% | −18.24% | 366 | −40.15% |
| | v2 | +0.43% | −18.67% | 530 | |
| | v2full | −7.23% | −19.96% | 758 | |

2022 holds under every version. Momentum's drawdown stays less than half of
buy & hold's, so that episode's protection reflects what momentum was
holding, not idle cash. COVID stays a case where momentum did worse, but the
"378 days to recover" figure is mostly idle cash: it is 124 days under v2.

### Regime interaction, three universes (`regime_interaction.csv`, `summary.json`)

Values are mean daily momentum − B&H, bullish minus bearish, against the v1
buy & hold rerun. CIs come from a 5,000-iteration block bootstrap.

| Universe | v1 rerun | v2 | v2full |
|---|---|---|---|
| US | −0.122% [−0.244, −0.011] **sig.** | −0.015% [−0.132, +0.082] | −0.060% [−0.171, +0.041] |
| Europe | +0.077% [+0.001, +0.159] **sig.** | +0.070% [+0.003, +0.136] **sig.** | +0.055% [−0.013, +0.118] |
| Emerging | −0.035% [−0.173, +0.100] | +0.023% [−0.099, +0.141] | −0.037% [−0.180, +0.097] |

### Verdicts under the pre-registered rule

**US.**
- **v2: Does not survive.** It keeps the same sign, but the CI includes 0
  and retained = 0.12 < 1/3. 2022 holds, but that doesn't override the
  interaction test.
- **v2full: Weakened.** It keeps the same sign, but the CI includes 0 and
  retained = 0.49, which is between 1/3 and 2/3. 2022 holds.

**Europe ("does not replicate").**
- **v2:** unchanged. The opposite-direction interaction is still significant.
- **v2full:** the rule's trigger fires, because Europe loses its
  significance (CI [−0.013, +0.118]). The point estimate barely moves
  (+0.077% → +0.055%), so it now reads as "nothing in Europe" rather than
  "a weak opposite signal". "Does not replicate" still stands.

**Emerging.**
- **v2 and v2full:** unchanged. It isn't significant in either version, and
  under v2 the sign isn't even in the US direction.

**Bottom line.** "Momentum's drawdown protection" in the US was mostly the
v1 engine leaving exit cash idle. With that cash invested, the bull/bear
asymmetry is no longer distinguishable from zero. The one robust protective
episode is 2022, where momentum's drawdown is about half of buy & hold's
under every engine version. Items 4–8 and 10–11 in the list below should be
corrected or retracted. Item 7 (2022) can stay, apart from its recovery time.

---

## README sentences that would need correcting

The README was not edited.

### Wrong now, regardless of the rerun (from reading the code)

1. §1: *"Fixing the sizer to normalise weights across concurrent signals
   brought the figure to 522%."*
   The code doesn't normalise. `begin_batch()` reserves cash once per bar,
   and `_cap_by_available_cash` fills signals first-come in `sorted(top)`
   ticker order until the reservation runs out. That prevents leverage but
   isn't normalisation, and it starves alphabetically later names.
2. Data and methodology, Sizing: *"a name realising 60% annualised vol
   receives roughly a third of the capital of one realising 20%."*
   With the defaults used everywhere (`target_annual_vol=0.15`,
   `max_weight=0.35`), weight = min(0.15/σ, 0.35). A 20%-vol name gets 0.35
   (capped) and a 60%-vol name gets 0.25, a ratio of about 0.71, not
   one-third. Every name under about 43% vol gets the same 0.35.
3. Limitations should gain an entry: the momentum book is not fully
   invested, through idle exit cash between rebalances (engine v1) and by
   design under vol targeting, and its realised β to buy & hold is 0.67
   (US), 0.84 (Europe) and 0.56 (Emerging).

### At stake: correct or retract depending on the v2 rerun

Section 3 already makes the interpretation of the first three items doubtful.

4. Title: *"Momentum's Drawdown Protection Is a US Phenomenon"*, and the
   intro line *"The pattern holds in the US sample."*
5. §3: *"The US shows the expected pattern with a confidence interval clear
   of zero."* The CI is correct as computed. What's at stake is reading it
   as momentum protection rather than lower exposure.
6. §2: *"So 'momentum protects in drawdowns' is true on average across US
   bearish days and misleading about the case that matters most."*
7. §2: *"In 2022 momentum lost roughly a seventh of what the benchmark
   lost."* and the 2022 row of the stress table (−4.81% / −18.24% / 366
   days).
8. §2: *"In the COVID crash it lost more and took 378 days to recover
   against the benchmark's 107."* and *"By the time the rebound came the
   strategy had rotated into defensives and missed it."* (See section 4: idle
   cash is an alternative mechanism.)
9. §1 table and *"The strategy did not beat the benchmark out of sample."*
   (+178.27% / −35.58%). Idle cash drags returns in a rising market, so the
   gap to buy & hold may shrink.
10. Distributional properties: *"its max drawdown (-35.58%) is shallower than
    buy & hold's (-41.35%) and it recovers in roughly two-thirds the time
    (378 days against 571), but its Calmar ratio (0.52) is still lower than
    buy & hold's (0.72)"*, and *"Every risk-adjusted ratio in the tearsheet's
    table — Sharpe, Sortino, Calmar — favors buy & hold; only the raw
    drawdown depth and recovery time favor momentum."*
11. *"Momentum pays its insurance premium far more often than it collects."*
    The "insurance" framing assumes the protection comes from the strategy
    itself.
12. §3 regime tables (annualised returns by regime, and the gap table) and
    the Europe paragraph (*"a weak signal in the opposite direction"*).
    Section 3 suggests Europe's opposite-direction effect is if anything
    understated once exposure is removed.

---

## Files

| Path | What |
|---|---|
| `quantbt/risk/sizing.py`, `quantbt/engine/backtest.py` | Opt-in `engine_version="v2"` and `full_investment`. Default unchanged. |
| `test_engine_v2.py`, `tests/` | Golden-fixture regression, plus v2 solvency, invested-fraction and timing tests |
| `run_cash_v2.py` | Drift check, v1/v2/v2full reruns, analysis → `results/v2/*.csv`, `summary.json`, `curves/` |
| `run_beta_diagnostic.py` → `results/v2/beta_diagnostic.csv` | The section 3 table, from published returns only |
