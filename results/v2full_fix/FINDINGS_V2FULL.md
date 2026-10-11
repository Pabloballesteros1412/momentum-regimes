# Appendix: v2full after the `full_investment` fix

This supersedes the v2full rows in `results/v2/` and the v2full verdict
("Weakened") in `results/v2/FINDINGS_CASH.md`. Those files are left as
they were written. v1 and v2 are unaffected by this fix: `full_investment`
is off for both, and their curves are read unchanged from
`results/v2/curves/`.

## What was wrong

`full_investment=True` rescaled every rebalance's long targets to
(1 − 2% buffer) of equity, including books whose vol-target weights already
summed past 100%. The vol-target weight is min(15% / vol, 35%), so a book
of four or more names usually sums to well over 100%. Instrumenting the
US 2015–2024 in-sample run showed **97% of 108 rebalances were scaled
*down***, with a median target of 138% gross. Plain v2 lets those books
take all available cash through its pro-rata cash cap. v2full instead
trimmed them to 98%, and the 2% buy and sell haircuts then took off a bit
more. It also trimmed held positions on every rebalance, which added
turnover. That is why v2full ended up *less* invested than v2.

## Fix

`PositionSizer._scale_to_full` now only scales **up**. If the scaling
factor is ≤ 1, the targets are left to v2's pro-rata cash cap. This is one
line, in `quantbt/risk/sizing.py`. `test_engine_v2.py` still passes,
including its v2full test (a 2-name book filled to about 97%).

## Validation: passed

The pass condition was that fixed v2full's mean invested fraction is ≥
v2's in every momentum book.

| Book | v1 | v2 | v2full (fixed) | v2full (before fix) |
|---|---|---|---|---|
| US 2015–24 walk-forward | 0.669 | 0.979 | 0.979 | 0.966 |
| US 2015–24 in-sample | 0.706 | 0.885 | 0.890 | 0.875 |
| US 2005–24 walk-forward | 0.816 | 0.986 | 0.986 | 0.971 |
| Europe 2005–24 walk-forward | 0.761 | 0.973 | 0.980 | 0.968 |
| Emerging 2005–24 walk-forward | 0.758 | 0.976 | 0.983 | 0.971 |

## Results (`regime_interaction.csv`, `headline_metrics_us2015.csv`, `stress_us2015.csv`, `summary.json`)

**US walk-forward.** Both studies are **identical to v2**. Every US
rebalance's vol-target book already summed to 100% or more, so the fix
leaves nothing to scale up.

| | US bull − bear gap | 95% CI | Retained | 2022 momentum max DD | Verdict |
|---|---|---|---|---|---|
| v2 | −0.015% | [−0.132, +0.082] | 0.12 | −18.67% | Does not survive |
| v2full (fixed) | −0.015% | [−0.132, +0.082] | 0.12 | −18.67% | **Does not survive** |
| v2full (before fix) | −0.060% | [−0.171, +0.041] | 0.49 | −19.96% | was "Weakened" |

The "Weakened" verdict came from the bug. With the fix, v2full reaches
the same verdict as v2.

**Europe.** +0.067% [−0.001, +0.133], which is no longer significant (it
was significant under v2). The rule's trigger ("Europe loses its
significance") fires under v2full, by a hair. "Does not replicate" stands.

**Emerging.** +0.015% [−0.104, +0.134], not significant. Unchanged.

**US in-sample.** +1,715% (v2: +1,559%). Max DD is the same at −32.41%.

## Decision

v2 stays the main result, because it changes only the bug. v2full is
reported here as an appendix: on this data, "fully invested" adds almost
nothing beyond fixing the idle exit cash.

Reproduce: `python run_v2full_fix.py` (reads v1/v2 from `results/v2/curves/`,
writes only to `results/v2full_fix/`).
