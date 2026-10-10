# 2022 deep dive: sector composition, and five US bear episodes (HYPOTHESES.md H4)

**Short answer.**

- **H4a passes, energy-driven.** Momentum's 2022 outperformance is almost
  entirely sector allocation (99.8% of the arithmetic excess), and energy
  is 55% of that allocation effect. On average through the 2022 drawdown,
  momentum held **42% energy against buy & hold's 0.7%**, and 26%
  healthcare against 2%. It was underweight consumer cyclicals: 9% against
  35%.
- **H4b: 2022 is the exception, not the rule.** With the fixed
  parameters, momentum beat buy & hold in only **1 of the other 4** bear
  episodes (the GFC). It lagged in 2011, COVID and (by 0.1 point) Q4 2018.
  Across all 12 grid parameter sets, every one beat buy & hold in 2022.
  For the other four episodes, 10 of 12 sets give "exception" and 2 give
  "mixed"; none gives "rule". The walk-forward replay, which covers the
  four post-2009 episodes, shows the same pattern: it beat buy & hold only
  in 2022.

## Episodes and series

| Episode | Window (S&P 500 peak → trough) |
|---|---|
| GFC | 2007-10-09 → 2009-03-09 |
| 2011 | 2011-04-29 → 2011-10-03 |
| Q4 2018 | 2018-09-20 → 2018-12-24 |
| COVID | 2020-02-19 → 2020-03-23 |
| 2022 | 2022-01-03 → 2022-10-12 |

- **Primary:** momentum v2 with fixed parameters (lookback 189, skip 21,
  top 10%), 2005–2024. That is the modal walk-forward choice, so it is
  **in-sample**.
- **Secondary:** the v2 walk-forward replay. It reproduces the stored
  curve to 3e-16 but starts in 2009, so it has no GFC.
- **Benchmark:** equal-weight buy & hold of the same 37 US names, on
  engine v2.

## Episode returns (`episodes.csv`)

| Episode | Momentum (fixed) | B&H | Excess | Mom max DD | B&H max DD | WF momentum | WF excess |
|---|---|---|---|---|---|---|---|
| GFC | −31.9% | −40.2% | **+8.4** | −42.1% | −45.1% | — | — |
| 2011 | −34.6% | −16.8% | −17.8 | −35.5% | −23.0% | −22.1% | −5.3 |
| Q4 2018 | −26.9% | −26.8% | −0.1 | −29.4% | −29.0% | −30.1% | −3.3 |
| COVID | −33.5% | −27.1% | −6.4 | −32.5% | −29.7% | −35.7% | −8.6 |
| 2022 | −7.3% | −42.4% | **+35.1** | −18.6% | −41.6% | −14.5% | **+27.9** |

## Attribution (`attribution_fixed.json`, `attribution_walkforward.json`)

These are daily Brinson terms, summed arithmetically over each episode.
The arithmetic sum is not the same as the compounded excess above. The
residual covers compounding, the open-versus-close timing of fills, and
costs.

| Episode | Allocation | of which energy | Selection | Cash | Sum of daily excess | Residual | Biggest active sector weights (mom vs B&H) |
|---|---|---|---|---|---|---|---|
| GFC | +7.7 | −1.0 | +13.3 | −0.3 | +14.2 | −6.4 | Defensive 18 vs 11, Cyclical 16 vs 10, Healthcare 0 vs 7 |
| 2011 | −6.3 | +0.1 | −15.5 | +0.1 | −23.0 | −1.3 | Comm. 32 vs 23, Healthcare 15 vs 5, Financials 2 vs 13 |
| Q4 2018 | −1.7 | −0.1 | +1.0 | +0.5 | +0.5 | +0.7 | Tech 46 vs 26, Comm. 23 vs 34, Financials 0 vs 14 |
| COVID | −5.2 | +0.2 | −2.6 | 0.0 | −7.8 | 0.0 | **Tech 87 vs 27**, Comm. 0 vs 32, Financials 0 vs 15 |
| **2022** | **+48.0** | **+26.5** | −0.9 | +1.0 | +44.6 | −3.5 | **Energy 42 vs 0.7**, Healthcare 26 vs 2, Cyclical 9 vs 35 |
| 2022 (WF) | +41.1 | +18.4 | −6.2 | +2.2 | +35.5 | −1.5 | Healthcare 32 vs 2, **Energy 29 vs 0.7**, Cyclical 7 vs 35 |

All values are percentage points, except the weights, which are average
percentage weights over the episode.

In the walk-forward series, energy is 45% of 2022's allocation effect,
just under the "energy-driven" threshold. There, healthcare and energy
together carry it.

## Reading it

- **2022 was a sector bet that paid.** Entering 2022, twelve-month winners
  were energy and healthcare, while buy & hold of these 37 names was
  dominated by tech, communication services and consumer cyclicals, the
  names that fell most. Within sectors, momentum's stock picks added
  nothing (selection −0.9 pt).
- **The same mechanism hurts when the winners are the ones that crash.**
  In COVID, momentum went in 87% tech and lagged. In 2011 it lagged badly
  through selection in communication services. Momentum protects when the
  previous year's leadership is defensive (energy in 2022, staples in
  2008). It doesn't otherwise.
- **The GFC is the other win,** and it comes mostly from *selection*
  (+13.3), not sector allocation. The large residual (−6.4) reflects
  compounding over a 17-month window.
- **This undercuts reading 2022 as evidence of protection.** It's one
  episode, explained by one sector rotation, in a universe that barely
  holds energy. On the point-in-time S&P 500 (`results/pit_us`), energy
  is a normal benchmark weight, and such a gap would be much smaller.

## Caveats

- The fixed parameters are in-sample. The 12-set robustness check is the
  guard against that.
- Sectors are today's Yahoo classification.
- With five episodes there is no statistical test, and none is claimed.

Reproduce with `python run_bear_episodes.py`.
