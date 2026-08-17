"""Statistical significance of the regime-conditional performance
differences produced by run_regimes.py.

Reads regime_returns_detail.csv (per-day return + regime label, per
universe and strategy) and runs quantbt.analytics.significance's block
bootstrap over every pairwise regime comparison, within each
universe/strategy. No backtests are rerun here -- this is pure analysis of
already-computed daily returns, so it's fast regardless of how long the
walk-forward that produced them took.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantbt.analytics.regimes import REGIME_LABELS
from quantbt.analytics.significance import bootstrap_regime_differences

RETURNS_CSV = Path("regime_returns_detail.csv")
OUTPUT_CSV = Path("regime_significance_results.csv")

N_ITERATIONS = 5000
BLOCK_SIZE = 20
CONFIDENCE = 0.95
MIN_EFFECTIVE_N = 30.0


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
    print(f"Loaded {len(detail):,} rows from {RETURNS_CSV}")
    print(f"Universes: {sorted(detail['universe'].unique())}")
    print(f"Strategies: {sorted(detail['strategy'].unique())}")
    print(
        f"Method: moving block bootstrap, block_size={BLOCK_SIZE} days, "
        f"n_iterations={N_ITERATIONS}, confidence={CONFIDENCE:.0%}\n"
    )

    OUTPUT_CSV.unlink(missing_ok=True)

    all_results = []
    n_significant = 0
    n_insufficient = 0
    n_null = 0

    for (universe, strategy), group in detail.groupby(["universe", "strategy"], sort=False):
        group = group.set_index("date").sort_index()
        result = bootstrap_regime_differences(
            group["return"], group["regime"], regimes=REGIME_LABELS,
            confidence=CONFIDENCE, block_size=BLOCK_SIZE, n_iterations=N_ITERATIONS,
            min_effective_n=MIN_EFFECTIVE_N, seed=0,
        )
        result.insert(0, "universe", universe)
        result.insert(1, "strategy", strategy)
        all_results.append(result)

        print(f"\n{'=' * 100}\n{universe} -- {strategy}\n{'=' * 100}")
        print(
            f"{'Regime A':<14}{'Regime B':<14}{'n_A':>6}{'n_B':>6}{'n_eff_A':>9}{'n_eff_B':>9}"
            f"{'Mean diff (daily)':>19}{'95% CI':>26}{'Verdict':>12}"
        )
        for _, row in result.iterrows():
            ci = f"[{_pct(row['ci_low'])}, {_pct(row['ci_high'])}]" if pd.notna(row["ci_low"]) else "n/a"
            verdict = "SIGNIFICANT" if row["significant"] else "not sig."
            print(
                f"{row['regime_a']:<14}{row['regime_b']:<14}{row['n_a']:>6}{row['n_b']:>6}"
                f"{_num(row['n_eff_a']):>9}{_num(row['n_eff_b']):>9}"
                f"{_pct(row['mean_diff']):>19}{ci:>26}{verdict:>12}"
            )
            print(f"    {row['note']}")

            if row["significant"]:
                n_significant += 1
            elif "insufficient" in row["note"]:
                n_insufficient += 1
            else:
                n_null += 1

    combined = pd.concat(all_results, ignore_index=True)
    combined.to_csv(OUTPUT_CSV, index=False)

    total = n_significant + n_insufficient + n_null
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Total pairwise regime comparisons: {total}")
    print(f"  Significant at {CONFIDENCE:.0%}                         : {n_significant}")
    print(f"  Not significant -- insufficient effective sample : {n_insufficient}")
    print(f"  Not significant -- no detectable difference      : {n_null}")
    print(f"\nFull results saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
