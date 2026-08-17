"""Walk-forward validation of the cross-sectional momentum strategy.

Compares three views of the same universe and period:

  1. In-sample    -- run_momentum.py's single, hand-picked parameter set,
                      backtested on the whole period it was chosen for.
  2. Walk-forward  -- rolling 4y-train / 1y-trade windows, re-selecting
                      parameters by in-sample Sharpe each fold and grading
                      them strictly out-of-sample, then stitched together.
  3. Buy & hold    -- the same universe, no timing or selection at all.

The gap between (1) and (2) is the in-sample overfitting that run_momentum.py's
single full-period backtest cannot reveal on its own.

Reuses TICKERS/START/END/run() from run_momentum.py and the parameter grid
from run_sensitivity.py, so it hits the same on-disk parquet cache -- no
network calls happen here.
"""

from __future__ import annotations

import itertools

from quantbt.data.handler import DataHandler
from quantbt.risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from quantbt.strategies.base import BuyAndHold
from quantbt.strategies.momentum import CrossSectionalMomentum
from quantbt.validation.walkforward import run_walkforward
from run_momentum import END, START, TICKERS
from run_momentum import run as run_backtest
from run_sensitivity import FRACTIONS, FREQUENCIES, LOOKBACKS, SKIPS

TRAIN_YEARS = 4
TRADE_YEARS = 1


def _param_grid() -> list[dict]:
    return [
        {"lookback": lookback, "skip": skip, "top_decile": fraction, "rebalance_freq": freq}
        for lookback, skip, fraction, freq in itertools.product(LOOKBACKS, SKIPS, FRACTIONS, FREQUENCIES)
    ]


def _report(label: str, total_return: float, max_drawdown: float) -> None:
    print(f"{label:<24} total return {total_return:>10.2%}   max drawdown {max_drawdown:>9.2%}")


def main() -> None:
    print(f"Universe ({len(TICKERS)} tickers), {START} -> {END}\n")

    frames = DataHandler.from_yfinance(TICKERS, START, END).frames
    param_grid = _param_grid()

    # Calendar-day buffer generous enough that the longest lookback in the
    # grid (in trading days) is always fully covered before trade_start.
    warmup_days = int(max(LOOKBACKS) * 7 / 5) + 30

    print(
        f"Running walk-forward (train={TRAIN_YEARS}y, trade={TRADE_YEARS}y, "
        f"{len(param_grid)} combinations per fold)...\n"
    )
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

    for i, fold in enumerate(wf_result.folds, start=1):
        p = fold.params
        print(
            f"Fold {i}: train [{fold.train_start.date()} -> {fold.train_end.date()})  "
            f"trade [{fold.trade_start.date()} -> {fold.trade_end.date()})  "
            f"best: lookback={p['lookback']:>3} skip={p['skip']:>2} "
            f"fraction={p['top_decile']:.1f} freq={p['rebalance_freq']:<9} "
            f"train_sharpe={fold.train_sharpe:>6.2f}"
        )

    wf_curve = wf_result.equity_curve
    wf_return = float(wf_curve["equity"].iloc[-1]) / wf_result.initial_capital - 1.0
    wf_drawdown = float(wf_curve["drawdown"].min())

    print("\nRunning in-sample momentum and buy & hold references...")
    _, _, is_result = run_backtest(CrossSectionalMomentum, VolatilityTargetSizer)
    is_curve = is_result.equity_curve()
    is_return = float(is_curve["equity"].iloc[-1]) / is_result.initial_capital - 1.0
    is_drawdown = float(is_curve["drawdown"].min())

    _, _, bh_result = run_backtest(BuyAndHold, EqualWeightSizer)
    bh_curve = bh_result.equity_curve()
    bh_return = float(bh_curve["equity"].iloc[-1]) / bh_result.initial_capital - 1.0
    bh_drawdown = float(bh_curve["drawdown"].min())

    print("\n" + "=" * 68)
    print(f"COMPARISON  ({START} -> {END})")
    print("=" * 68)
    _report("In-sample momentum", is_return, is_drawdown)
    _report("Walk-forward momentum", wf_return, wf_drawdown)
    _report("Buy & hold", bh_return, bh_drawdown)
    print("-" * 68)
    degradation = (is_return - wf_return) * 100.0
    print(f"In-sample -> walk-forward degradation : {degradation:>8.2f} pp")
    print("=" * 68)


if __name__ == "__main__":
    main()
