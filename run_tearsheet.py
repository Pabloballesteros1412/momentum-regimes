"""Generates a comparative tearsheet PNG for the three equity curves already
used in this project: momentum in-sample (run_momentum.py), momentum
walk-forward (run_walkforward.py), and buy & hold -- all on the same
37-ticker universe and period.

Recomputes the three backtests via the same functions those scripts use, so
this hits the same on-disk parquet cache (no network calls) and always
reflects the current strategy/sizer code.
"""

from __future__ import annotations

import itertools

from quantbt.analytics.tearsheet import generate_tearsheet
from quantbt.data.handler import DataHandler
from quantbt.risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from quantbt.strategies.base import BuyAndHold
from quantbt.strategies.momentum import CrossSectionalMomentum
from quantbt.validation.walkforward import run_walkforward
from run_momentum import END, START, TICKERS
from run_momentum import run as run_backtest
from run_sensitivity import FRACTIONS, FREQUENCIES, LOOKBACKS, SKIPS
from run_walkforward import TRADE_YEARS, TRAIN_YEARS

OUTPUT_PNG = "tearsheet.png"


def _param_grid() -> list[dict]:
    return [
        {"lookback": lookback, "skip": skip, "top_decile": fraction, "rebalance_freq": freq}
        for lookback, skip, fraction, freq in itertools.product(LOOKBACKS, SKIPS, FRACTIONS, FREQUENCIES)
    ]


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

    print(f"\nRendering tearsheet to {OUTPUT_PNG}...")
    generate_tearsheet(
        equity_curves,
        OUTPUT_PNG,
        title="Momentum vs Buy & Hold -- 37-Ticker Universe",
    )
    print(f"Saved {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
