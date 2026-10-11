"""Rerun only the v2full momentum books after the full_investment fix.

full_investment used to rescale every long book to (1 - buffer) of equity,
including the ~97% of rebalances whose vol-target weights already summed
past 100% -- scaling those DOWN and leaving v2full less invested than v2.
It now only scales up (quantbt/risk/sizing.py, PositionSizer._scale_to_full).

This reuses run_cash_v2's stages unchanged but writes to results/v2full_fix/,
so results/v2/ (made before the fix) is never overwritten. v1 and v2 curves
are read from results/v2/curves/ -- the fix cannot change them, because
full_investment is off for both -- and only the v2full curves are rerun.

    python run_v2full_fix.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

import run_cash_v2 as rc

OLD_CURVES = rc.CURVES
rc.OUT = Path("results/v2full_fix")
rc.CURVES = rc.OUT / "curves"


def _resolve(name: str) -> Path:
    if "v2full" in name:
        return rc.CURVES / f"{name}.csv"
    return OLD_CURVES / f"{name}.csv"


rc._have = lambda name: _resolve(name).exists()
rc._load_curve = lambda name: rc.pd.read_csv(_resolve(name), index_col="date", parse_dates=["date"],
                                             float_precision="round_trip")


def main() -> None:
    rc.CURVES.mkdir(parents=True, exist_ok=True)
    shutil.copy(OLD_CURVES.parent / "spy_regime_rerun.csv", rc.OUT / "spy_regime_rerun.csv")
    rc._log("=== stage: runs (v2full only)")
    rc.stage_runs()
    rc._log("=== stage: analyze")
    rc.stage_analyze()


if __name__ == "__main__":
    main()
