# How much of momentum's drawdown protection survives once it is fully invested?

**Short answer, as far as the published data allows:** in the US, nearly
none of it is distinguishable from holding less equity. The published US
regime interaction, where momentum beats buy & hold in bear markets and lags
it in bull markets, is reproduced at **93%** by a portfolio that simply holds
**67% buy & hold and 33% cash**. Once that constant exposure is removed, the
remaining US interaction is −0.009% per day, with a 95% CI of
[−0.103%, +0.070%]. That isn't significant.

**What is not answered yet:** how much of that low exposure comes from the
idle-exit-cash bug and how much from intended design, meaning vol-target cash
and low-beta stock picks. Answering that needs the v1/v2 reruns. They are
implemented and tested but haven't run, because this environment can't reach
Yahoo Finance (see "Status"). No number in this document comes from a rerun.

---

## Status

| Step | State |
|---|---|
| 1. Invested fraction on real data | **Blocked.** Needs price data. Holdings aren't in any published file, so this can't be inferred from returns. |
| 2. Engine v2, opt-in, with an exact default-path test | **Done.** `python test_engine_v2.py` |
| 3. v2 rerun vs published | **Blocked.** Same reason. `python run_cash_v2.py` does everything, including the drift check. |
| 4. This document | Answered from published returns only (the exposure diagnostic below). The idle-cash split is pending. |
| 5. README sentences | Listed below. README untouched. |

**Blocker:** this cloud environment's network policy denies
`query1.finance.yahoo.com` and `query2.finance.yahoo.com` (HTTP 403 at the
egress proxy). There's no `cache/` in the repo. Once either is available,
this command fills every pending table in `results/v2/`:

```bash
python run_cash_v2.py        # stages: drift -> runs -> analyze (resumable)
```

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
| `run_cash_v2.py` | Drift check, v1/v2/v2full reruns, analysis → `results/v2/*.csv` (pending data) |
| `run_beta_diagnostic.py` → `results/v2/beta_diagnostic.csv` | The section 3 table, from published returns only |
