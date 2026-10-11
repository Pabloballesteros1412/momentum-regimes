# Morning summary — night 2 (2026-10-11)

All 11 tasks are done on `claude/fervent-faraday-oz0knf`, with a pushed
checkpoint after each. A few failures came up along the way (see "What
failed"), and each was resolved.

- **Safety checks.** Nothing was merged. `README.md`, the published CSVs,
  `tearsheet.png` and every existing results folder are byte-identical to
  before. The one addition to an existing folder is the
  `results/pit_us/RENAME_MAP.md` you asked for. New runs each have their
  own folder.
- **Tests.** All 34 pass (`pytest test_*.py`), with 92% line coverage of
  `quantbt`.
- **Pre-registration.** Every new test was written into `HYPOTHESES.md`
  (H1, H3–H8) and committed before it ran.
- **PR #2.** Not watched, as asked. It now carries tonight's commits
  too.

**The paper is `PAPER_v2.md`. It's the best single thing to read
first.**

## Headline

1. **On a point-in-time S&P 500, the US regime effect is significant in
   the *opposite* direction to "protection".**
   - Momentum minus the benchmark, bull days minus bear days: +0.075%/day
     on 2009–24, 95% CI [+0.003, +0.152]. That is H1, pre-registered;
     it passes narrowly.
   - Over 2000–24: +0.082%/day [+0.023, +0.130] (H8).
   - Momentum lost 27% in the dot-com bust against the benchmark's 10%,
     and missed the 2009 rebound (+12% against +45%).
2. **2022 was a sector bet and the exception.**
   - Allocation explains 99.8% of momentum's 2022 excess. Energy is 55%
     of that: 42% weight against 0.7% for buy & hold.
   - Momentum beat buy & hold in only 1 of the other 4 US bear episodes
     (H4).
3. **The engine reproduces the academic factor.**
   - The point-in-time active return correlates 0.71 monthly with
     Fama-French UMD. There is no alpha beyond FF5+UMD.
   - The fixed 37-name buy & hold has **11.8% a year of FF5+UMD alpha
     (t = 4.4)**: the hindsight in choosing that list, measured
     directly (H5).
4. **The "1 of 96 parameter sets beats buy & hold" result was the bug.**
   - Under v2, 40 of 96 beat it (in-sample).
   - The regime null holds at every cost from 0 to 50 bp.
   - Momentum's lower max drawdown is not reliable: P(shallower) is about
     0.5 (H7).
5. **Long-only volatility scaling doesn't fix momentum crashes.** It cuts
   crash drawdowns on the 37 names but *significantly lowers* Sharpe on
   the point-in-time universe (−0.09), because it de-risks just before
   rebounds (H6).

## Task by task

| # | Task | Result | Folder / file |
|---|---|---|---|
| 1 | Rename map | 20 mappings, each with EDGAR evidence (old name on the same CIK) and 100% price continuity. Coverage 74.3% → 76.7%. Results barely move. **H1a passes** (+0.075%/day, CI [0.003, 0.152]). | `results/pit_us/RENAME_MAP.md`, `results/pit_us_renamed/` |
| 2 | v2 tearsheet | `tearsheet_v2.png`, drawn from the persisted v2 curves; old tearsheet kept | `run_tearsheet_v2.py` |
| 3 | Sector attribution under v2 | **H3: partly holds (3/4 orderings).** US tech/cyclicals and Europe healthcare tilts hold; energy ordering and the concentration argument don't. The published v1 shares counted *selected* names (7/8 reproduced exactly); v1 often never bought them. | `results/sector_v2/` |
| 4 | 2022 deep dive, five bear episodes | **H4a passes, energy-driven. H4b: exception** (1/4 other episodes; 10/12 parameter sets "exception", 2 "mixed") | `results/bear_episodes/` |
| 5 | FF5 + UMD | **H5a pass** (US v2 UMD 0.54, t 21.9; PIT 0.46, t 29.7). **H5d pass** (v2 beta > v1 everywhere). H5b: PIT tracks UMD well (0.71); 37-name books track partly (≈0.3). | `results/factors/` |
| 6 | Vol-scaled momentum | US: **H6a pass** (2009 rebound DD −4.3% vs −18.3%), H6b n.s. PIT: H6a passes by negligible margins; **H6b significant against** (Sharpe −0.09) | `results/volscaled/` |
| 7 | Robustness | **H7a pass** (40/96 vs 1/96). **H7b robust null**, no cost break-even (momentum trails buy & hold even at 0 bp). **H7c**: max DD not reliably shallower | `results/robustness_v2/` |
| 8 | US from 2000 | 2000–04 coverage 49.7% (above the 40% flag). **H8a pass**; no dot-com protection | `results/pit_us_2000/` |
| 9 | Engineering | CI workflow (`.github/workflows/tests.yml`), 13 new tests, coverage 59% → 92%, docstrings and type hints on every public `quantbt` function. **Two real bugs found and fixed** (below). | `test_*.py`, `pytest.ini` |
| 10 | Web explorer | `web/index.html`, a no-dependency static page. Universe/strategy/regime pickers, log equity and drawdown vs buy & hold with regime shading, tooltip, metrics table; light/dark. Checked at 1200 px and 390 px. | `web/` |
| 11 | Paper | `PAPER_v2.md`: full working-paper draft with tables and references | |

## Decisions I made

- **Rename-map rule made stricter twice, before H1 ran** (documented in
  RENAME_MAP.md and HYPOTHESES-consistent):
  - "Name changed at the swap date" was dropped as sufficient. It accepted
    acquisitions where the acquirer renamed itself (SunTrust→Truist,
    Mylan→Viatris).
  - Substring name matching was replaced by a strict token rule. It had
    accepted Twitter→ITT.
- **Old company names came from a hand list** when Wikipedia's change
  table lacked them. Every name was still verified on EDGAR.
- **Sector attribution** uses Yahoo's sector field as of today, and the
  same "share of bearish rebalances holding ≥1 name" metric as the
  original. Value weights are reported too.
- **The bear-episode study needs 2008.** The walk-forward starts in 2009,
  so the primary series is fixed-parameter momentum (in-sample modal
  parameters), labelled as such. It has a 12-parameter-set robustness
  check and a walk-forward replay cross-check.
- **Factor regressions use regional factors.** Europe uses Europe
  factors and Emerging uses Emerging factors (monthly only), rather than
  US factors.
- **Cost sensitivity uses a flat one-way cost.** It replaces the default
  friction model and applies during parameter selection too. That needed
  an opt-in `broker_factory` argument in `run_walkforward`; the default
  path is unchanged and the golden test passes.
- **Vol scaling is applied to the whole book,** not per name, because
  engine v2's cash cap would otherwise undo it. There is no leverage, and
  the targets were fixed in advance, not tuned.
- **The extended sample** uses its own data folder (`results/pit_us_2000/data`)
  and cache (`cache/pit1996`), so `data/` was not overwritten.
- **SEC requests:** my first test request to EDGAR mistakenly sent your
  email address in its User-Agent header. Every later request used a
  placeholder address.

## What failed (and what I did)

- **Two engine bugs found by the new tests, both fixed.**
  - `metrics.sharpe_ratio` returned about 1e16 for a constant series,
    because float-noise variance wasn't treated as zero.
  - `export.clean` turned `NaT` into the string `"NaT"`. No exported file
    was affected.
- **Two wait loops matched their own command line** and stalled the job
  queue for about 15 minutes before I noticed. No results were affected.
- **The PIT vol-scaled run crashed once** on a `super()` error in the run
  script's PIT subclass. I fixed it and reran it from scratch.
- **Rename coverage is limited.** 154 candidate targets have no current
  EDGAR record (themselves delisted), and acquired or bankrupt names
  can't be priced from free data. That leaves 23% of member-days missing.
- **The 1996+ build differs slightly from the 2005+ build.** It excludes
  10 reused tickers instead of 5, so its 2009–24 numbers differ a little
  from `pit_us_renamed` (13.4% against 14.0% momentum CAGR). Noted in its
  findings.

## Next steps (prioritised)

1. **Decide the paper's main universe.** I'd make the point-in-time
   S&P 500 the main US result and the 37-name list the robustness check.
   Then replace README.md with README_v2 updated to that framing, after
   your review.
2. **Get delisted prices** (CRSP via WRDS, or Tiingo with a key) for the
   remaining 23% of member-days, which are mostly failures. That is the
   biggest open bias. H1's narrow CI makes it worth doing before
   publishing the sign flip.
3. **A like-for-like liquid-40 benchmark** (equal weight of the same 40
   names). It separates the breadth effect from survivorship cleanly.
4. **Long-short momentum** (or a levered vol-scaled book) to test
   Barroso & Santa-Clara and Daniel & Moskowitz on their own terms. The
   long-only results here say little about the factor itself.
5. **A point-in-time Europe universe** (Euro Stoxx 50 from 2010) to see
   whether Europe's opposite-sign interaction survives point-in-time
   data, as the US one does.
6. **Host the web explorer** (GitHub Pages from `web/`), and add the
   point-in-time and extended series to the export.

---

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
