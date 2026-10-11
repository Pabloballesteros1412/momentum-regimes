"""How much of the published regime interaction is just lower equity exposure?

Uses only the published regime_returns_detail.csv -- no new backtests, no
network. For each universe, over the days both strategies have a return:

  beta       OLS slope of walk-forward momentum's daily return on buy &
             hold's (full overlap, so this is a hindsight diagnostic, not a
             tradable rule).
  exposure   the interaction a portfolio holding `beta` in buy & hold and
             the rest in cash would show, (beta - 1) * B&H's mean daily
             return, bullish minus bearish. Any book running below full
             equity exposure -- idle exit cash, vol-target cash, or simply
             low-beta stock picks -- produces this pattern mechanically.
  residual   the interaction left in (momentum - beta * B&H), block
             bootstrapped exactly as run_interaction_significance.py does.
             This is the part a constant lower exposure cannot explain:
             timing, conditional beta, stock selection.

It cannot say WHICH source the low exposure comes from; run_cash_v2.py
(which needs price data) separates idle cash from the rest.

Writes results/v2/beta_diagnostic.csv.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from quantbt.analytics.significance import bootstrap_regime_differences

RETURNS_CSV = Path("regime_returns_detail.csv")
PUBLISHED = Path("regime_interaction_significance.csv")
OUTPUT = Path("results/v2/beta_diagnostic.csv")


def main() -> None:
    detail = pd.read_csv(RETURNS_CSV, parse_dates=["date"], float_precision="round_trip")
    published = pd.read_csv(PUBLISHED).set_index("universe")
    rows = []
    for universe in dict.fromkeys(detail["universe"]):
        g = detail[detail["universe"] == universe]
        bh = g[g["strategy"] == "Buy & hold"].set_index("date")
        wf = g[g["strategy"] == "Walk-forward momentum"].set_index("date")
        a = pd.DataFrame({"b": bh["return"], "m": wf["return"], "regime": bh["regime"]}).dropna()
        trend = a["regime"].str.split("_").str[0]

        beta = float(np.cov(a["m"], a["b"])[0, 1] / a["b"].var())
        beta_by_trend = {
            t: float(np.cov(a.loc[trend == t, "m"], a.loc[trend == t, "b"])[0, 1] / a.loc[trend == t, "b"].var())
            for t in ("bullish", "bearish")
        }
        b_bull, b_bear = a.loc[trend == "bullish", "b"].mean(), a.loc[trend == "bearish", "b"].mean()
        exposure_diff = (beta - 1.0) * (b_bull - b_bear)

        res = bootstrap_regime_differences(a["m"] - beta * a["b"], trend, ["bullish", "bearish"],
                                           block_size=20, n_iterations=5000, seed=0).iloc[0]
        pub = published.loc[universe]
        rows.append({
            "universe": universe, "days": len(a), "beta_full": beta,
            "beta_bullish": beta_by_trend["bullish"], "beta_bearish": beta_by_trend["bearish"],
            "published_diff": pub["mean_diff"], "published_ci_low": pub["ci_low"], "published_ci_high": pub["ci_high"],
            "exposure_only_diff": exposure_diff,
            "exposure_share_of_published": exposure_diff / pub["mean_diff"],
            "residual_diff": res["mean_diff"], "residual_ci_low": res["ci_low"], "residual_ci_high": res["ci_high"],
            "residual_significant": bool(res["significant"]),
        })

    out = pd.DataFrame(rows)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT, index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(out.to_string(index=False))


if __name__ == "__main__":
    main()
