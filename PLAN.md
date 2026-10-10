# PLAN: point-in-time universes, a second strategy, and a JSON export

Status: proposal only. No code has changed. Nothing in this plan overwrites
the published results: `README.md`, `tearsheet.png`, `regime_*.csv` and
`sensitivity_results.csv` stay exactly as they are. Every new run writes to new
paths under `results/` (see "Ground rules").

Effort is given in focused working days for one person. It does not include
wall-clock compute, which is listed separately where it matters.

---

## 0. Ground rules and findings from reading the repo

These apply to all three items and come from reading the current code.

**G1. Don't overwrite the published CSVs.** `run_regimes.py` and the two
significance scripts call `unlink()` on their output CSVs at startup
(`run_regimes.py:249`, `run_significance.py:53`,
`run_interaction_significance.py:70`), so running them again silently replaces
the published results. New work must not reuse those scripts with their default
paths. Plan: add an optional `--out-dir` argument whose default keeps today's
behaviour, or write new scripts that import the shared pieces (`UNIVERSES`,
`_param_grid`, `regime_breakdown`) and write under `results/<experiment>/`.

**G2. Data drift.** `cache/` is gitignored, so a fresh clone downloads
whatever Yahoo serves today. Adjusted prices are revised after the fact when
dividends are re-adjusted or splits are corrected, so a rerun will not
reproduce the published numbers bit for bit. Every new experiment that reruns a
backtest should start with a **drift check**: rerun buy & hold for each universe
and compare its daily returns with the stored `Buy & hold` rows in
`regime_returns_detail.csv`, using correlation, total-return difference and the
dates of the largest daily deviations. The tolerance is reported, not hidden.
Comparisons such as "PIT vs fixed" or "reversal vs momentum" must use the
*rerun* baseline, not the published one, so that drift doesn't pass as an
effect.

**G3. Sizer cash drag (observed, not fixed here).** `PositionSizer.begin_batch()`
reserves `portfolio.cash` *before* the bar's EXIT orders settle, and
`_cap_by_available_cash` does not add sell proceeds back. On a rebalance day,
new entries can only use cash that was already idle. Exit proceeds then sit
uninvested until the next rebalance, a month later. A quick synthetic check
(30 GBM names, 126-day momentum, top 20%, `VolatilityTargetSizer`) gave an
average invested fraction of **0.72**, with some months starting at about 0.40.
This doesn't invalidate the published comparison, which is internally
consistent. But:
- it biases momentum against buy & hold (B&H never rotates), and
- it will bias a high-turnover strategy (item 2) even more.

The README also says the sizer was fixed to "normalise weights across
concurrent signals". The code does sequential cash capping in alphabetical
ticker order (`sorted(top)` in `momentum.py`), which is not the same thing.
**Recommendation:** treat a fix as a separate, explicitly versioned change
(engine v2). Report the invested fraction for every strategy in items 1 and 2.
Never mix runs from before and after the fix in one comparison. This plan does
not change the sizer.

**G4. There is no paper file in the repo.** "The published paper" is taken to
mean `README.md` plus its figure and CSVs. All three items leave them untouched.
Any new findings go in a new document, for example `results/README.md`.

---

## 1. Survivorship bias: point-in-time universes

### Problem

Every universe is a fixed list chosen in 2025 (`run_momentum.TICKERS`,
`run_regimes.EUROPE_TICKERS`, `run_regimes.EMERGING_TICKERS`). A real fix needs
two separate things, and free data covers them very unevenly:

- **(a) Membership:** which names were in the index on each date.
- **(b) Prices for names that left:** delisted, acquired, bankrupt or renamed.

### What's free, by universe

| Need | US | Europe | Emerging |
|---|---|---|---|
| (a) Historical constituents | **Feasible.** The `fja05680/sp500` GitHub repo publishes daily S&P 500 membership from 1996, rebuilt from Wikipedia's change log plus archived lists. Wikipedia's "List of S&P 500 companies" change table is a cross-check. Quality is good from the mid-2000s; there are known gaps and errors in ticker spellings. | **Partial.** Wikipedia's Euro Stoxx 50 page has some change history, which isn't complete or reliable before about 2010. Nothing free for STOXX 600 or a broad index. | **Not feasible.** MSCI EM membership is licensed. No credible free source. |
| (b) Prices of delisted names | **Partial.** yfinance mostly drops delisted tickers and reuses symbols (a 2008 symbol can point to a different company today). Tiingo's free tier keeps many delisted US tickers, but its quotas (around 500 unique symbols a month, hourly and daily request caps) mean a backfill over several weeks. Stooq has patchy delisted coverage. CRSP via WRDS is the gold standard and is free only with academic access. | **Mostly not feasible.** Delisted European local listings are almost never kept by free sources. | **Not feasible.** Delisted ADRs, such as the 2021 Chinese SOE delistings named in `run_regimes.py`, are gone from free sources or survive only as patchy OTC histories. |

### Honest bottom line

- **US: a mostly point-in-time S&P 500 universe is achievable**, with a
  measurable gap: the share of index-weight-days for which no price could be
  found. Expect a few percent of member-days to stay missing even after
  Tiingo, mostly early bankruptcies and small acquired names. The gap gets
  reported; it isn't plugged with assumptions.
- **Europe and Emerging: survivorship bias can't be fixed for free.** The
  realistic deliverable is to **quantify** it, not remove it:
  1. Measure the size of the bias in the US (PIT vs the fixed 37 names, same
     engine, same period). Report it as an order of magnitude whose sign is
     expected to carry over to Europe and EM, not as a correction.
  2. In Europe, optionally run a Euro Stoxx 50 universe with point-in-time
     membership from 2010 onward, using names that still have prices. This
     fixes selection on *membership* but not on *survival*. Label it that way.
  3. Add a sensitivity that injects a delisting return for names whose price
     series ends early (Shumway 1997 uses -30% for performance-related
     delistings) and shows how far the headline gaps move.
- **The study's comparison is momentum *minus* buy & hold on the same
  universe, so part of the bias cancels.** It doesn't cancel fully: momentum
  is more exposed, because it buys recent winners and some of those
  subsequently delist. Item 1 should state this plainly instead of claiming
  either full cancellation or a full fix.

### Engine changes needed even for the US case

These are the non-obvious parts. The engine assumes every symbol lives for
the whole sample.

1. **Membership mask.** Add a `UniverseSchedule` (date → set of members) and
   make it available to strategies, for example
   `DataHandler.is_member(symbol)`, capped at `current_time` like everything
   else. `CrossSectionalMomentum.on_market` ranks over `self.data.symbols`
   today; it must rank only over current members. Make this an opt-in
   constructor argument so the default behaviour, and therefore the published
   results, doesn't change.
2. **Delisting handling.** Today, if a held name's data ends:
   `Portfolio.mark_to_market` keeps marking it at its last close forever,
   because `get_latest_close` returns the last visible bar. Meanwhile
   `broker.execute` rejects the EXIT because there's no next open. The position
   becomes a frozen, unsellable asset. Fix: when a symbol has no further bars,
   force-liquidate at the last close, optionally applying the delisting-return
   assumption above, and log it.
3. **Benchmark.** `BuyAndHold` buys every symbol the first time it has data and
   never sells. With a PIT universe it would accumulate every name that ever
   joined. It needs a PIT variant: equal-weight current members, rebalanced
   monthly. `EqualWeightSizer` also divides by `len(self.data.symbols)`, which
   would be several hundred historical names. It needs to divide by the current
   member count.
4. **Ticker mapping.** Membership lists use the ticker in force at the time
   (FB, ANTM, ...), while price sources use the current one or a per-source
   ID. Add a small mapping table, `data/ticker_map.csv`, and a check that every
   member-day resolves to exactly one price series.
5. **Scale.** About 500 members at a time and about 1,000+ distinct names over
   2005–2024, against 37 today. `DataHandler.get_latest_bars` slices by label
   on every call. `SignalCache` already handles the momentum score. The broker
   and sizer still call `get_latest_bars` per order, which is fine. Budget
   compute: the 12-combination grid × 16 folds over about 500 names is
   probably 10–20× today's US runtime. That's acceptable, but needs checking
   on one fold first.

### Files affected

- New: `quantbt/data/universe.py` (`UniverseSchedule`, loaders for the
  fja05680 CSV and the ticker map), `quantbt/data/sources/tiingo.py` (a
  cached downloader with quota handling; API key from an environment variable,
  never committed), `data/sp500_membership.csv`, `data/ticker_map.csv`.
- Changed, opt-in only with defaults preserved: `quantbt/data/handler.py`
  (an optional schedule, a source-aware cache key so Yahoo and Tiingo parquet
  files never collide, and not raising on empty downloads when a schedule is
  in use), `quantbt/strategies/momentum.py` (an optional membership filter),
  `quantbt/strategies/base.py` (`PointInTimeEqualWeight` benchmark),
  `quantbt/risk/sizing.py` (an optional member count),
  `quantbt/portfolio/portfolio.py` and `quantbt/engine/backtest.py` (forced
  liquidation on end-of-data).
- New scripts: `build_universe_us.py` (membership, mapping, coverage report),
  `run_regimes_pit.py` → `results/pit_us/*.csv`.
- Tests: `test_universe.py` covering: a strategy never ranks a non-member;
  delisted positions are liquidated; with an "always-member" schedule the
  results match the fixed-universe run exactly. The last one is a regression
  guard that the opt-in path doesn't change today's behaviour.

### Steps

1. Download and freeze the fja05680 snapshot with its commit hash. Build the
   ticker map. Produce a coverage report: member-days with a price from
   yfinance, from Tiingo, and with none.
2. Make the engine changes behind flags, and write the tests above first.
3. Run the drift check (G2), then fixed-37 and PIT-S&P500 under the same
   engine, same period and same grid.
4. Write `results/pit_us/README.md` covering the size of the bias, the
   coverage gap, and the delisting-return sensitivity.
5. Optional: Euro Stoxx 50 membership-only PIT from 2010.

### Risks

- **Coverage gaps aren't random.** Missing names are disproportionately the
  ones that failed, so the PIT result is still biased upward, only less. Report
  coverage weighted by index weight if possible, or by name-days if not.
- **Ticker reuse and mapping errors** can silently splice two companies.
  Mitigation: reject any series with an implausible gap or jump at the mapping
  boundary, and spot-check the 20 largest contributors by hand.
- **Free-tier terms and quotas change.** Freeze downloaded data in the cache
  and record the source and date per symbol.
- **The new US universe changes the experiment.** 500 names with top-decile
  selection gives about 50 holdings against about 4–7 today. That changes
  concentration, which the README already flags as entangled with the result.
  Run a "PIT, but restricted to the largest ~40 members by trailing dollar
  volume" variant too, so the bias effect can be separated from the breadth
  effect.
- **Engine changes can leak into the published path.** The flag defaults and
  the always-member regression test are the guard.

### Effort

- US constituents and ticker mapping: 2–3 days.
- Delisted price backfill: 2 days of work, plus 1–3 weeks of wall-clock time
  under Tiingo's free quotas.
- Engine changes and tests: 3–4 days.
- Runs and write-up: 2 days.
- Euro Stoxx 50 variant: +2 days.

**Total: about 2 weeks of work, plus quota-bound download time.**

---

## 2. A second strategy under the same regime framework

### Recommendation: short-term reversal, not value

**Why not value.** Value needs book-to-market, earnings yield or something
similar, **as known at each historical date**. The free route (yfinance) offers
roughly four years of statements and a *current* snapshot of ratios. Backfilling
2005–2024 value scores from it would be a textbook look-ahead, against the
engine's whole design principle that there must be no API path to future data.
Price-only "value" proxies, such as 3–5 year long-term reversal (De Bondt &
Thaler 1985), are a different factor that is only loosely related to B/M. They
would also consume five years of warm-up, wiping out the early walk-forward
folds, including the 2008 crisis. Point-in-time fundamentals (Compustat,
Worldscope) are commercial.

**Why reversal.**
1. **It's purely price-based.** It runs on the existing data, cache, `SignalCache`
   and walk-forward machinery with no new data dependency. So it carries the
   *same* survivorship bias as momentum and doesn't add a new one, which keeps
   the comparison clean.
2. **It gives a sharp, opposite-signed hypothesis for the regime framework.**
   Reversal profits are usually interpreted as payment for providing liquidity,
   and they rise when volatility and stress are high (Nagel 2012, "Evaporating
   Liquidity"). Momentum crashes in exactly those rebounds (Daniel & Moskowitz
   2016, already cited). The prediction: reversal's edge over buy & hold should
   be *larger* in high-volatility regimes, where momentum's is weakest. That
   gives the volatility axis, which the README notes "adds no separation", a
   real test.
3. **It's already in the story.** The 12-1 skip month exists *because* of
   short-term reversal. Showing that component as its own strategy across
   regimes and markets follows naturally.
4. **It's cheap to implement.** The ranking logic is momentum's with the sign
   flipped and a short window.

**Stated plainly in the write-up:** in large, liquid names with retail-style
costs, long-only reversal is known to be weak or negative after costs. A null
result is a plausible outcome and still informative.

### Design (kept symmetric with momentum)

- **Signal:** trailing return over `lookback` days (5, 10 or 21), optionally
  skipping the most recent day (`skip` 0 or 1) to limit bid-ask bounce. Long
  the *bottom* fraction (0.1 or 0.2). Monthly rebalance, same as momentum.
  That's a 3 × 2 × 2 = **12-combination grid**, the same size as momentum's
  reduced grid, so the walk-forward search budget is the same.
- **Sizing, costs and validation:** `VolatilityTargetSizer`, the same broker
  frictions, and the same 4y/1y walk-forward with Sharpe selection over the
  same 16 folds. Warm-up can be much shorter, but keep the same `warmup_days`
  so both strategies trade the identical out-of-sample calendar.
- **Regimes and significance:** the same SPY regimes, the same block bootstrap
  (20-day blocks, 5,000 iterations, seed 0). Tests:
  1. Reversal minus B&H, bullish vs bearish. This mirrors
     `run_interaction_significance.py`.
  2. Reversal minus B&H, high vs low volatility. This is the new hypothesis.
  3. **Reversal minus momentum** by regime. This is the head-to-head the item
     is really about.
- **Multiple testing:** this roughly doubles the number of reported tests.
  Report raw CIs plus a Holm-adjusted column, and say which conclusions
  survive.

### Files affected

- New: `quantbt/strategies/reversal.py`, holding `ShortTermReversal`. Implement
  it as a subclass of `CrossSectionalMomentum` that negates the score, so it
  reuses `SignalCache.momentum_score` and the rebalance logic. **`momentum.py`
  itself is not modified.**
- New: `run_regimes_reversal.py`, which imports `UNIVERSES`,
  `regime_breakdown`, `TRAIN_YEARS` and `TRADE_YEARS`, and writes
  `results/reversal/{folds,breakdown,returns_detail}.csv`. It also reruns B&H
  for the drift check (G2) and reruns momentum, so all three series come from
  the same data snapshot.
- New: `run_strategy_comparison.py`, which runs the three bootstrap tests
  above and writes `results/reversal/interaction_significance.csv`.
- Optional, preserving current behaviour: an `--out-dir` and a `--strategy`
  argument on the existing significance scripts instead of new copies.
- Tests: `test_reversal.py`. On synthetic data where one name drops sharply in
  the last `lookback` days, that name must be selected. With the sign flipped
  back, the selection must equal momentum's.

### Steps

1. Implement `ShortTermReversal` and its unit test.
2. Run a smoke test on one fold, one universe. Check turnover, costs and the
   invested fraction (see G3).
3. Full run: three universes × (B&H, momentum, reversal) into `results/reversal/`.
4. Run the significance scripts and write `results/reversal/README.md`.

### Risks

- **Turnover and costs dominate.** About 100% monthly turnover on 4–8 names.
  Report gross and net figures (the broker already tracks commission and
  slippage separately) so a negative net result can be traced to costs.
- **G3 cash drag hits reversal harder than momentum,** because it exits more
  names per rebalance. Without care, "reversal underperforms" could just mean
  "the sizer leaves reversal half in cash". Mitigations: report the invested
  fraction per strategy and regime, and if they differ materially, flag the
  comparison as not like-for-like until an engine-v2 sizer fix is agreed.
- **Concentration:** 0.1 of 37 names is about 4 holdings, so idiosyncratic
  noise is large. Same caveat as momentum, stated once for both.
- **Same regime reference (SPY) for all universes:** inherited and unchanged,
  so comparable with the published tables.

### Effort

- Strategy and tests: 1 day.
- Scripts and smoke test: 1 day.
- Full runs: the same compute as the published `run_regimes.py`, plus one B&H
  and momentum rerun for the drift check.
- Significance and write-up: 1–2 days.

**Total: about 4 days of work.**

---

## 3. Export precomputed results to JSON for a static page

### Principle

The export is **read-only over persisted results**. It reruns no backtests, so
it can't drift (G2) and can't change any published number. Every series the
page needs for the three-universe study can be rebuilt from
`regime_returns_detail.csv`:

- the equity curve is the cumulative product of (1 + daily return),
- drawdown is equity divided by its running maximum, minus 1,
- full-period metrics come from `metrics.compute_metrics`,
- per-regime metrics are read straight from `regime_breakdown_partial.csv`,
- folds and significance come from their CSVs.

### Output layout (`web/data/`)

```
manifest.json            schema_version, generated_at, git commit, source files + sha256,
                         universes, strategies, regimes, periods, caveats (survivorship,
                         FX, SPY regime reference, sizer note)
regimes.json             {dates: [...], label: [...]}       # SPY regime per day, for shading
equity/{universe}.json   {dates: [...], series: {<strategy>: {equity: [...], drawdown: [...]}}}
metrics.json             [{universe, strategy, window: "full"|"common", <compute_metrics fields>}]
regime_metrics.json      [{universe, strategy, regime, days, annual_return, annual_vol,
                           max_drawdown, sharpe}]
significance.json        {regime_vs_regime: [...], interaction: [...]}
folds.json               [{universe, fold_index, train/trade dates, params, train_sharpe,
                           oos_return, oos_max_drawdown}]
```

Experiments from items 1 and 2 export into `web/data/<experiment>/` with the
same schema, listed in `manifest.json`. The page can then switch between
"published", "reversal" and "pit_us" without any special cases.

### Format decisions

- **Columnar arrays** (one `dates` array, parallel value arrays) instead of
  one object per day. About 5,000 days × 3 universes × 2–3 strategies is
  roughly 300–500 KB with 6-decimal rounding, which is fine for a static page.
  Add an optional `--weekly` downsampled copy for fast first paint.
- **Strict JSON:** `allow_nan=False`, with NaN converted to `null` explicitly.
  Dates as ISO `YYYY-MM-DD`. Returns as decimals, not percentages. The units
  go in the manifest.
- **Two metric windows per strategy:** `full` (B&H covers 2005–2024; WF
  momentum covers 2009–2024 because of the first training window) and `common`
  (the overlapping out-of-sample days only). Without that, a page that puts
  them side by side compares different periods. The README's regime tables
  already use overlapping days, so `common` matches them.
- **Equity rebased to 1.0** at each series' first date. Absolute dollar levels
  carry no information here, and rebasing avoids implying that the 2009
  WF start has the same capital as B&H.

### Validation (makes "doesn't change results" checkable)

`test_export.py` reloads the JSON and asserts:
- per-regime annual returns equal the README §3 table to the printed
  precision (for example, US WF bullish_low = 26.75%),
- interaction CIs equal `regime_interaction_significance.csv`,
- rebuilt per-regime CAGR from `regime_returns_detail.csv` equals
  `regime_breakdown_partial.csv`, a consistency check between the two
  persisted files,
- every JSON file parses with a strict parser (no NaN or Infinity).

### Scope note: the US 2015–2024 results (README §1–2)

The in-sample, 96-combination walk-forward and B&H curves behind
`tearsheet.png` and the stress table were **never persisted**, only printed or
rendered. Exporting them means a rerun, which hits G2.

Proposal: phase 3b adds `--persist results/us_2015_2024/` to `run_walkforward.py`
and `run_stress.py`, with the default off, reruns them, and exports **only if**
the rerun reproduces the README's headline figures within a stated tolerance
(for example, WF total return 178.27% ± 1 pp). If it doesn't, the page shows
the three-universe study only and says why.

### Files affected

- New: `export_results.py`, `quantbt/analytics/export.py` (pure functions:
  returns → equity and drawdown, dataframe → columnar dict, NaN → null),
  `test_export.py`, `web/data/` (generated, committed so the static page needs
  no build step).
- Phase 3b, optional: an opt-in `--persist` on `run_walkforward.py` and
  `run_stress.py`.
- Not touched: every existing CSV, `README.md`, `tearsheet.png`.

### Steps

1. Write `quantbt/analytics/export.py` and its unit tests.
2. Write `export_results.py` for the published three-universe study.
3. Add `test_export.py` with the README cross-checks.
4. Hook items 1 and 2 into the same exporter as each lands.
5. Optional: phase 3b.

### Risks

- **Silent mismatch between the page and the paper,** for example from window
  misalignment or rounding. Mitigation: the README cross-check tests, and the
  `common` window.
- **Schema churn once a page depends on it.** Mitigation: `schema_version` in
  the manifest, and add fields only, never rename.
- **Committed generated files go stale.** Mitigation: the manifest records
  source-file hashes, and the test fails if they don't match the CSVs in the
  repo.

### Effort

- Exporter, schema and tests: 1.5–2 days.
- Phase 3b, if pursued: +1 day plus a walk-forward rerun.

---

## Suggested order

1. **Item 3 first.** It's low risk and read-only, and it fixes the output
   format before new experiments produce data.
2. **Item 2 next.** It's cheap and needs no new data. It should land with the
   G3 invested-fraction diagnostics, which decide whether the sizer fix needs
   to come before a fair comparison.
3. **Item 1 last.** It's the most valuable for credibility, but has the
   longest lead time because of quota-bound downloads. Start the US data
   backfill (step 1) in parallel with item 2, since it's mostly waiting.

| Item | Work | Main risk |
|---|---|---|
| 1. PIT universes (US real fix; EU/EM quantified, not fixed) | ~2 weeks + download time | Non-random coverage gaps; ticker mapping |
| 2. Short-term reversal | ~4 days | Costs and sizer cash drag dominate the comparison |
| 3. JSON export | ~2 days | Page and paper drifting apart (mitigated by tests) |
