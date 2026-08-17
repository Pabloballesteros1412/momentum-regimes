"""Sensitivity sweep for the cross-sectional momentum strategy.

Runs a full backtest for every combination of lookback, skip, universe
fraction and rebalance frequency, and records return/risk/cost metrics for
each into sensitivity_results.csv.

Reuses TICKERS/START/END from run_momentum.py, so this hits the same
on-disk parquet cache in cache/ that run_momentum.py already populated --
no network calls happen here as long as that cache exists.
"""

from __future__ import annotations

import itertools

import pandas as pd

from quantbt.data.handler import DataHandler
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from quantbt.strategies.base import BuyAndHold
from quantbt.strategies.momentum import CrossSectionalMomentum
from run_momentum import END, START, TICKERS

LOOKBACKS = [126, 189, 252, 315]
SKIPS = [0, 10, 21, 42]
FRACTIONS = [0.1, 0.2, 0.3]
FREQUENCIES = ["monthly", "quarterly"]

OUTPUT_CSV = "sensitivity_results.csv"


def _metrics(result: Portfolio, **params) -> dict:
    curve = result.equity_curve()
    final = float(curve["equity"].iloc[-1])

    return {
        **params,
        "total_return": final / result.initial_capital - 1.0,
        "max_drawdown": float(curve["drawdown"].min()),
        "annualized_vol": float(curve["returns"].std() * (252 ** 0.5)),
        "friction_cost": result.total_commission + result.total_slippage,
    }


def run_momentum_backtest(lookback: int, skip: int, fraction: float, freq: str) -> dict:
    data = DataHandler.from_yfinance(TICKERS, START, END)
    portfolio = Portfolio(data, initial_capital=100_000.0)
    strategy = CrossSectionalMomentum(
        data, lookback=lookback, skip=skip, top_decile=fraction, rebalance_freq=freq
    )
    sizer = VolatilityTargetSizer(data, portfolio)
    broker = SimulatedBroker(data)

    backtest = Backtest(data, strategy, sizer, broker, portfolio, verbose=False)
    result = backtest.run()
    return _metrics(
        result, lookback=lookback, skip=skip, fraction=fraction, rebalance_freq=freq
    )


def run_buy_and_hold_baseline() -> dict:
    data = DataHandler.from_yfinance(TICKERS, START, END)
    portfolio = Portfolio(data, initial_capital=100_000.0)
    strategy = BuyAndHold(data)
    sizer = EqualWeightSizer(data, portfolio)
    broker = SimulatedBroker(data)

    backtest = Backtest(data, strategy, sizer, broker, portfolio, verbose=False)
    result = backtest.run()
    return _metrics(result)


def main() -> None:
    print("Running buy & hold baseline...")
    baseline_return = run_buy_and_hold_baseline()["total_return"]
    print(f"Buy & hold total return: {baseline_return:.2%}\n")

    combos = list(itertools.product(LOOKBACKS, SKIPS, FRACTIONS, FREQUENCIES))
    rows = []
    for i, (lookback, skip, fraction, freq) in enumerate(combos, start=1):
        metrics = run_momentum_backtest(lookback, skip, fraction, freq)
        rows.append(metrics)
        print(
            f"[{i:>3}/{len(combos)}] lookback={lookback:>3} skip={skip:>2} "
            f"fraction={fraction:.1f} freq={freq:<9} "
            f"return={metrics['total_return']:>9.2%}"
        )

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {len(df)} combinations to {OUTPUT_CSV}")

    beats = int((df["total_return"] > baseline_return).sum())
    trails = len(df) - beats

    print("\n" + "=" * 62)
    print(f"Buy & hold benchmark return : {baseline_return:>10.2%}")
    print(f"Combinations that BEAT it   : {beats:>4} / {len(df)}")
    print(f"Combinations that TRAIL it  : {trails:>4} / {len(df)}")
    print("=" * 62)


if __name__ == "__main__":
    main()
