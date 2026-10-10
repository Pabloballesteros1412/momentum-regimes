"""tearsheet_v2.png: the README tearsheet redrawn from the engine-v2 curves.

Reads the persisted US 2015-2024 curves in results/v2/curves/ (in-sample
momentum v2, walk-forward momentum v2, buy & hold) -- no backtest is rerun,
so the figure matches README_v2.md's numbers exactly. tearsheet.png (engine
v1) is left as it is.

    python run_tearsheet_v2.py
"""

from __future__ import annotations

import pandas as pd

from quantbt.analytics.tearsheet import generate_tearsheet

CURVES = "results/v2/curves"
OUTPUT_PNG = "tearsheet_v2.png"


def _equity(name: str) -> pd.Series:
    df = pd.read_csv(f"{CURVES}/{name}.csv", index_col="date", parse_dates=["date"], float_precision="round_trip")
    return df["equity"]


def main() -> None:
    curves = {
        "In-sample momentum (v2)": _equity("us2015_is_momentum_v2"),
        "Walk-forward momentum (v2)": _equity("us2015_wf_momentum_v2"),
        "Buy & hold": _equity("us2015_buyhold_v2"),
    }
    generate_tearsheet(curves, OUTPUT_PNG, title="Momentum vs Buy & Hold -- 37-Ticker Universe (engine v2)")
    print(f"Saved {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
