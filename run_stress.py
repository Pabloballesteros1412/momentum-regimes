"""Stress-tests the three equity curves (in-sample momentum, walk-forward
momentum, buy & hold) against isolated historical windows: the COVID crash,
the COVID recovery, the 2022 bear market, and the 2023 rally.

Recomputes the three backtests the same way run_tearsheet.py does, so this
hits the same on-disk parquet cache -- no network calls happen here.
"""

from __future__ import annotations

import itertools

import pandas as pd

from quantbt.data.handler import DataHandler
from quantbt.risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from quantbt.strategies.base import BuyAndHold
from quantbt.strategies.momentum import CrossSectionalMomentum
from quantbt.validation.stress import STRESS_WINDOWS, run_stress_test
from quantbt.validation.walkforward import run_walkforward
from run_momentum import END, START, TICKERS
from run_momentum import run as run_backtest
from run_sensitivity import FRACTIONS, FREQUENCIES, LOOKBACKS, SKIPS
from run_walkforward import TRADE_YEARS, TRAIN_YEARS


def _param_grid() -> list[dict]:
    return [
        {"lookback": lookback, "skip": skip, "top_decile": fraction, "rebalance_freq": freq}
        for lookback, skip, fraction, freq in itertools.product(LOOKBACKS, SKIPS, FRACTIONS, FREQUENCIES)
    ]


def _pct(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{x:.2%}"


def _days(x) -> str:
    return "not yet" if x is None or (isinstance(x, float) and pd.isna(x)) else f"{int(x):,d}d"


def main() -> None:
    print(f"Universe ({len(TICKERS)} tickers), {START} -> {END}\n")

    print("Running in-sample momentum...")
    _, _, is_result = run_backtest(CrossSectionalMomentum, VolatilityTargetSizer)

    print("Running buy & hold...")
    _, _, bh_result = run_backtest(BuyAndHold, EqualWeightSizer)

    param_grid = _param_grid()
    warmup_days = int(max(LOOKBACKS) * 7 / 5) + 30
    print(
        f"Running walk-forward momentum (train={TRAIN_YEARS}y, trade={TRADE_YEARS}y, "
        f"{len(param_grid)} combinations per fold -- this takes a few minutes)..."
    )
    frames = DataHandler.from_yfinance(TICKERS, START, END).frames
    wf_result = run_walkforward(
        frames=frames,
        param_grid=param_grid,
        strategy_factory=CrossSectionalMomentum,
        sizer_factory=VolatilityTargetSizer,
        train_years=TRAIN_YEARS,
        trade_years=TRADE_YEARS,
        initial_capital=100_000.0,
        warmup_days=warmup_days,
        trade_extra_kwargs=lambda trade_start: {"active_from": trade_start},
    )

    equity_curves = {
        "In-sample momentum": is_result.equity_curve()["equity"],
        "Walk-forward momentum": wf_result.equity_curve["equity"],
        "Buy & hold": bh_result.equity_curve()["equity"],
    }

    report = run_stress_test(equity_curves)

    col_w = 24
    print("\n" + "=" * (col_w + 4 * 12))
    print("STRESS TEST -- isolated historical windows")
    print("=" * (col_w + 4 * 12))

    for window in STRESS_WINDOWS:
        rows = report[report["window"] == window.name]
        print(f"\n{window.name}  ({window.start} -> {window.end})")
        print("-" * (col_w + 4 * 12))
        print(f"{'Strategy':<{col_w}}{'Return':>12}{'Max DD':>12}{'Worst day':>12}{'Recovery':>12}")
        for _, row in rows.iterrows():
            if not row["has_data"]:
                print(f"{row['strategy']:<{col_w}}{'no data':>12}")
                continue
            print(
                f"{row['strategy']:<{col_w}}"
                f"{_pct(row['return']):>12}"
                f"{_pct(row['max_drawdown']):>12}"
                f"{_pct(row['worst_day']):>12}"
                f"{_days(row['days_to_recover']):>12}"
            )

    print("\n" + "=" * (col_w + 4 * 12))


if __name__ == "__main__":
    main()
