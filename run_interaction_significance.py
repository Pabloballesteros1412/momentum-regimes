"""Interaction-effect significance: does momentum walk-forward's excess
return over buy & hold change with the market regime?

run_significance.py's regime-vs-regime contrasts compare a single
strategy's OWN returns across regimes -- which mostly just confirms that
momentum returns more when the market is up than when it's down, a close
to tautological finding. The question that actually matters for whether
regime should inform strategy choice is different: is momentum's edge
over buy & hold (their daily return difference) itself regime-dependent,
or statistically indistinguishable regardless of what the market is doing?

For each universe: build the daily (momentum - buy & hold) return
difference over the walk-forward's own out-of-sample window (the only
period both strategies have a return to difference), collapse the
four-way regime label to trend only (bullish/bearish) -- run_significance.py
already showed bearish_low vs bearish_high never separates in any
universe/strategy, so splitting by volatility here would only spend
sample size without adding information -- and bootstrap whether the mean
difference-of-differences is distinguishable between the two trends.

Reads regime_returns_detail.csv (written by run_regimes.py); reruns no
backtests.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantbt.analytics.significance import bootstrap_regime_differences

RETURNS_CSV = Path("regime_returns_detail.csv")
OUTPUT_CSV = Path("regime_interaction_significance.csv")

N_ITERATIONS = 5000
BLOCK_SIZE = 20
CONFIDENCE = 0.95
MIN_EFFECTIVE_N = 30.0

TREND_LABELS = ["bullish", "bearish"]
BUYHOLD = "Buy & hold"
MOMENTUM = "Walk-forward momentum"


def _pct(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{x:.3%}"


def _num(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{x:.1f}"


def main() -> None:
    if not RETURNS_CSV.exists():
        raise FileNotFoundError(
            f"{RETURNS_CSV} not found -- run run_regimes.py first (it writes this as a partial result)"
        )

    detail = pd.read_csv(RETURNS_CSV, parse_dates=["date"])
    universes = list(dict.fromkeys(detail["universe"]))
    print(f"Loaded {len(detail):,} rows from {RETURNS_CSV}")
    print(f"Universes: {universes}")
    print(
        f"Method: moving block bootstrap, block_size={BLOCK_SIZE} days, "
        f"n_iterations={N_ITERATIONS}, confidence={CONFIDENCE:.0%}, "
        f"regime collapsed to {TREND_LABELS}\n"
    )

    OUTPUT_CSV.unlink(missing_ok=True)
    all_results = []

    for universe in universes:
        group = detail[detail["universe"] == universe]
        bh = group[group["strategy"] == BUYHOLD].set_index("date")
        wf = group[group["strategy"] == MOMENTUM].set_index("date")

        aligned = pd.DataFrame(
            {"buyhold": bh["return"], "momentum": wf["return"], "regime": bh["regime"]}
        ).dropna(subset=["buyhold", "momentum"])

        # bh and wf were built from the same shared SPY-regime series in
        # run_regimes.py, so on any date both have a return the regime
        # label must agree -- verify that rather than assume it.
        check = pd.DataFrame({"bh_regime": bh["regime"], "wf_regime": wf["regime"]}).dropna()
        mismatched = check["bh_regime"] != check["wf_regime"]
        assert not mismatched.any(), f"{universe}: buy&hold/momentum regime labels disagree on {mismatched.sum()} dates"

        diff = aligned["momentum"] - aligned["buyhold"]
        collapsed_regime = aligned["regime"].str.split("_").str[0]  # "bearish_high" -> "bearish"

        result = bootstrap_regime_differences(
            diff, collapsed_regime, regimes=TREND_LABELS,
            confidence=CONFIDENCE, block_size=BLOCK_SIZE, n_iterations=N_ITERATIONS,
            min_effective_n=MIN_EFFECTIVE_N, seed=0,
        )
        result.insert(0, "universe", universe)
        all_results.append(result)

        span = f"{aligned.index.min().date()} -> {aligned.index.max().date()}"
        print(f"\n{'=' * 100}\n{universe}  (momentum - buy&hold daily diff, {len(aligned):,} overlapping days, {span})\n{'=' * 100}")
        print(
            f"{'Trend A':<10}{'Trend B':<10}{'n_A':>7}{'n_B':>7}{'n_eff_A':>9}{'n_eff_B':>9}"
            f"{'Mean(diff|A)':>14}{'Mean(diff|B)':>14}{'A-B diff':>12}{'95% CI':>26}{'Verdict':>14}"
        )
        for _, row in result.iterrows():
            ci = f"[{_pct(row['ci_low'])}, {_pct(row['ci_high'])}]" if pd.notna(row["ci_low"]) else "n/a"
            verdict = "SIGNIFICANT" if row["significant"] else "not sig."
            print(
                f"{row['regime_a']:<10}{row['regime_b']:<10}{row['n_a']:>7}{row['n_b']:>7}"
                f"{_num(row['n_eff_a']):>9}{_num(row['n_eff_b']):>9}"
                f"{_pct(row['mean_daily_a']):>14}{_pct(row['mean_daily_b']):>14}"
                f"{_pct(row['mean_diff']):>12}{ci:>26}{verdict:>14}"
            )
            print(f"    {row['note']}")

    combined = pd.concat(all_results, ignore_index=True)
    combined.to_csv(OUTPUT_CSV, index=False)

    n_sig = int(combined["significant"].sum())
    print("\n" + "=" * 100)
    print("SUMMARY -- is momentum's edge over buy & hold regime-dependent?")
    print("=" * 100)
    for _, row in combined.iterrows():
        verdict = "YES, significant interaction" if row["significant"] else "no significant interaction detected"
        print(f"  {row['universe']:<10} bullish vs bearish: {verdict}  (95% CI [{_pct(row['ci_low'])}, {_pct(row['ci_high'])}])")
    print(f"\n{n_sig}/{len(combined)} universes show a statistically significant regime interaction.")
    print(f"Full results saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
