"""End-to-end smoke test of the engine using synthetic geometric Brownian motion.

Purpose: confirm that a buy-and-hold run through the full event loop tracks the
underlying asset return, minus a small drag from commissions and slippage. If
the tracking error is large, something in the ordering or bookkeeping is wrong.
"""

import numpy as np
import pandas as pd

from quantbt.data.handler import DataHandler
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.risk.sizing import EqualWeightSizer
from quantbt.strategies.base import BuyAndHold


def synthetic_frame(seed: int, n: int = 500, s0: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n, name="timestamp")

    daily_returns = rng.normal(0.0004, 0.015, n)
    close = s0 * np.exp(np.cumsum(daily_returns))

    open_ = close * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n)))
    volume = rng.integers(2_000_000, 8_000_000, n)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


def main() -> None:
    frames = {"AAA": synthetic_frame(1), "BBB": synthetic_frame(2, s0=45.0)}
    data = DataHandler(frames)

    portfolio = Portfolio(data, initial_capital=100_000.0)
    strategy = BuyAndHold(data)
    sizer = EqualWeightSizer(data, portfolio)
    broker = SimulatedBroker(data)

    backtest = Backtest(data, strategy, sizer, broker, portfolio, verbose=True)
    result = backtest.run()

    curve = result.equity_curve()
    final = float(curve["equity"].iloc[-1])
    total_return = final / result.initial_capital - 1.0

    # Reference: what an equal-weight, frictionless hold would have returned.
    benchmark = np.mean(
        [float(df["close"].iloc[-1] / df["open"].iloc[1] - 1.0) for df in frames.values()]
    )

    print("\n" + "=" * 62)
    print("PIPELINE SMOKE TEST")
    print("=" * 62)
    print(f"Signals generated      : {backtest.signal_count}")
    print(f"Orders submitted       : {backtest.order_count}")
    print(f"Orders filled          : {backtest.fill_count}")
    print(f"Orders rejected        : {len(broker.rejected)}")
    print("-" * 62)
    print(f"Initial capital        : {result.initial_capital:>14,.2f}")
    print(f"Final equity           : {final:>14,.2f}")
    print(f"Total return           : {total_return:>14.2%}")
    print(f"Frictionless benchmark : {benchmark:>14.2%}")
    print(f"Tracking difference    : {total_return - benchmark:>14.2%}")
    print("-" * 62)
    print(f"Total commission paid  : {result.total_commission:>14,.2f}")
    print(f"Total slippage cost    : {result.total_slippage:>14,.2f}")
    print(f"Maximum drawdown       : {curve['drawdown'].min():>14.2%}")
    print(f"Residual cash          : {result.cash:>14,.2f}")
    print("=" * 62)

    assert result.cash >= 0, "Cash went negative: sizing exceeded available capital"
    assert backtest.fill_count > 0, "No fills occurred: the pipeline is broken"
    print("\nAll structural checks passed.")


if __name__ == "__main__":
    main()
