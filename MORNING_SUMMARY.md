# Morning summary (overnight, 2026-10-10)

All six tasks are done, on branch `claude/fervent-faraday-oz0knf`, with a
pushed checkpoint after each. `README.md`, the published CSVs,
`tearsheet.png` and `results/v2/` are unchanged; this was checked against
`main` and against the `results/v2` commit. Nothing was merged. All six
test files pass on the final branch: `test_pipeline`, `test_engine_v2`,
`test_reversal`, `test_universe`, `test_export`, `test_regimes`.

## Headline

1. **The published US "drawdown protection" was the idle-cash bug.**
   Under engine v2 it does not survive the pre-registered rule: retained
   0.12, CI [−0.132%, +0.082%]. That holds for v2full as well, once
   v2full was fixed.
2. **2022 is the one real protective episode.** Momentum's max drawdown
   was −18.7% against buy & hold's −40.2%, under every engine version.
3. **Reversal doesn't help.** 0 of 24 pre-registered regime tests are
   significant after Holm. Reversal's Sharpe is below buy & hold's in all
   three markets.
4. **Survivorship bias is large in the US.** On a point-in-time S&P 500,
   with 74% of member-days priced, momentum's 2009–24 CAGR falls from
   27.2% to 13.7% and the benchmark's from 29.7% to 14.0%. The US bull/bear
   interaction becomes *significant in the opposite direction*: momentum
   lags in bear markets, as in Europe. This is exploratory.

## Task by task

### 1. v2full less invested than v2: fixed, and only v2full rerun

- **Cause:** `full_investment` rescaled every book to 98% of equity,
  including the **97% of US rebalances** whose vol-target weights already
  summed past 100% (median 138%). So it scaled them *down*, the 2%
  haircuts then took off more, and held names were trimmed on every
  rebalance.
- **Fix:** scale up only, one line in `quantbt/risk/sizing.py`.
  `run_v2full_fix.py` reruns only the v2full curves into
  `results/v2full_fix/`.
- **Validation passed:** v2full is ≥ v2 invested in every book.
- **US:** v2full is now identical to v2. Its verdict changes from
  "Weakened" (an artefact of the bug) to **Does not survive**.
- **Europe:** v2full loses significance by a hair (CI lower bound
  −0.0006%). **Emerging:** unchanged.
- **Doc:** `results/v2full_fix/FINDINGS_V2FULL.md`. It supersedes the
  v2full rows in `results/v2/`, which were left as written.

### 2. pyarrow added to `requirements.txt` (`pyarrow>=14.0`)

### 3. `README_v2.md` drafted

- **New title:** "Momentum's Drawdown Protection Was Mostly Idle Cash".
- It has the same structure and tone as README.md, with v2 numbers
  throughout:
  - US 2015–24: WF +419.9% / −36.6%; B&H +1,254.8% / −41.4%.
  - COVID: −17.5%, recovers in 124 days (not 378).
  - 2022: +0.4%, max DD −18.7%.
  - Regime tables and the interaction table for all three markets.
- New "Correction" section: the bug, the pre-registered rule, how the
  verdict changed, and two README claims that were wrong regardless of the
  rerun.
- I added one limitation sentence pointing to the task 6 result after it
  landed.
- `tearsheet.png` was **not** regenerated (it's v1). README_v2 says so.

### 4. Short-term reversal: `results/reversal/FINDINGS_REVERSAL.md`

- **Setup:**
  - `ShortTermReversal` (momentum with the score negated) on engine v2.
  - 12-combination grid: lookback 5/10/21 × skip 0/1 × fraction 0.1/0.2.
  - Same folds, warm-up and regimes as momentum.
  - **The data check passed:** buy & hold v2 reproduces `results/v2`
    exactly.
- **Test family:** 24 tests (reversal vs B&H and vs momentum, by trend,
  by volatility, and within each regime), committed *before* the run.
  Block-bootstrap p-values, Holm-adjusted.
- **0 of 24 are significant after Holm.** 3 are significant before
  correction, about what chance gives. The Nagel high-vol prediction gets
  no support.
- **CAGR 2009–24:**

  | | Reversal | Momentum | B&H |
  |---|---|---|---|
  | US | 17.6% | 27.2% | 29.7% |
  | Europe | 12.6% | 10.8% | 12.8% |
  | Emerging | 7.6% | 7.1% | 12.6% |

- **Costs:** 0.75–2.3% a year for reversal, against 0.24–0.67% for
  momentum.

### 5. JSON export: `web/data/v2/` (1.3 MB)

- `export_results.py` + `quantbt/analytics/export.py`. It is read-only
  over persisted results and covers v2 momentum, reversal and buy & hold.
- Files: manifest (source SHA-256s), regimes, per-universe equity and
  drawdown, full and common-window metrics, regime metrics, both
  significance tables, folds, and the US 2015–24 headline and stress
  tables.
- `test_export.py` checks every exported number against its CSV, and
  rebuilds per-regime CAGR from daily returns.
- **One check failed on the first run and was fixed.** The exporter's
  "common" window kept European trading days with no SPY regime label,
  which the tables drop. I aligned the exporter to the tables'
  definition. This was a bug in the new exporter, not in the results.
  Documented in the commit and the manifest.

### 6. Point-in-time S&P 500, US: `results/pit_us/FINDINGS_PIT.md`

- **Membership:** fja05680/sp500 at commit `a2430f2`. 943 names were
  members in 2005–24.
- **Prices:** Yahoo only. Stooq is blocked here, and Tiingo needs a key.
- **Coverage:**
  - 74.3% of member-days have a price, from 53% in 2005 to 96% in 2024.
  - 351 names are missing entirely, including 17 still members in 2024
    but since acquired or renamed.
  - 5 reused tickers were excluded.
- **Engine pieces (opt-in, tested):** `UniverseSchedule`,
  `PointInTimeMomentum`, a PIT equal-weight benchmark, liquidation when a
  name's data ends, and a 40-most-liquid breadth control.
- **Results, 2009–24:**

  | | Fixed 37 names | PIT S&P 500 |
  |---|---|---|
  | Momentum CAGR | 27.2% | 13.7% |
  | Benchmark CAGR | 29.7% | 14.0% |
  | Interaction | −0.015% (n.s.) | **+0.081% [+0.009, +0.156]** |

  - The liquid-40 control shows the same sign (+0.149%, significant).

## Decisions I made

- **Fast-forwarded this branch onto `claude/cash-redeploy-v2`** (earlier,
  for the first run). It carries PR #1's commits, which is why PR #1 is
  closed in favour of the new PR.
- **Rerun outputs went to new folders** (`results/v2full_fix/`,
  `results/reversal/`, `results/pit_us/`) so `results/v2/` is never
  overwritten. v1/v2 curves are reused from `results/v2/curves/`.
- **v2 is the main result in README_v2**, and v2full is an appendix,
  because v2 changes only the bug.
- **Reversal:** I chose the test family myself (T1–T5 per universe) and
  committed it before running. Holm is applied across all 24 tests, not
  per universe, which is the stricter choice.
- **Reversal head-to-head uses momentum v2 and B&H v2** from
  `results/v2`, so there is one snapshot and one engine for all three
  strategies.
- **PIT:**
  - Dropped the −30% delisting-return sensitivity. It can't trigger,
    because every Yahoo series runs to the end of 2024.
  - Added the liquid-40 breadth control from PLAN.md's risk list.
  - Did **not** build a rename map: each mapping needs a manual
    splice check.
  - The PIT interaction tests are exploratory (not pre-registered).
- **Export covers v2 only.** The published v1 results stay in their CSVs
  and aren't duplicated into JSON.

## What failed or was skipped

- Nothing blocked a task.
- The exporter's common-window mismatch was caught by its own test and
  fixed (task 5).
- Delisting-return sensitivity: not run (see above).
- `tearsheet.png` was not regenerated for v2.
- The sector-attribution analysis in README §3 was not recomputed under
  v2; README_v2 says so.
- Prices for the PIT universe live in `cache/pit/` (gitignored), so a
  fresh clone must rerun `build_universe_us.py`. Yahoo may have dropped
  more names by then, so coverage would change.

## What I recommend next

1. **Review README_v2.md** and decide whether it replaces README.md. If
   so, regenerate the tearsheet from `results/v2/curves/`.
2. **Build a verified rename map** for the PIT universe (ANTM→ELV,
   PKI→RVTY, BLL→BALL, MYL→VTRS, SYMC→GEN, …). It is likely the
   cheapest big coverage gain. Then rerun `run_regimes_pit.py`.
3. **Get delisted prices** (a Tiingo key, or CRSP through WRDS if you have
   academic access). With them, the delisting sensitivity and the PIT
   interaction become credible.
4. **Pre-register the PIT interaction test** before any rerun with better
   coverage. The current sign flip is the most interesting open finding,
   and it was found after the fact.
5. Consider making the PIT S&P 500 the main US universe in the paper,
   with the fixed list as the robustness check rather than the other way
   round.
