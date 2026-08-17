"""Cross-sectional 12-1 momentum vs. buy-and-hold on a real-data universe.

SURVIVORSHIP BIAS WARNING
--------------------------------------------------------------------------
TICKERS below is a FIXED, PRESENT-DAY list of large, liquid names spread
across sectors -- it is NOT a point-in-time constituent list. Every ticker
here is one that we already know traded continuously and stayed liquid
through 2015-2024; anything that was delisted, went bankrupt, got acquired,
or dropped out of relevance during that window is silently absent, because
picking it required hindsight the strategy would not have had in 2015.
That is textbook survivorship bias. Both the momentum strategy and the
buy-and-hold benchmark below are run on this same biased universe, so the
comparison between them is fair, but the absolute return numbers are
optimistic relative to what a point-in-time, all-constituents backtest
would produce. Do not treat this as a claim about real historical
performance -- it is an illustration of the pipeline only.
--------------------------------------------------------------------------
"""

from __future__ import annotations

from quantbt.data.handler import DataHandler
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from quantbt.strategies.base import BuyAndHold
from quantbt.strategies.momentum import CrossSectionalMomentum

TICKERS = [
    # Technology
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ORCL", "CRM", "ADBE",
    # Consumer discretionary
    "AMZN", "TSLA", "HD", "MCD", "NKE",
    # Consumer staples
    "PG", "KO", "PEP", "WMT", "COST",
    # Healthcare
    "JNJ", "UNH", "PFE", "ABBV", "MRK",
    # Financials
    "JPM", "BAC", "GS", "V", "MA",
    # Energy
    "XOM", "CVX",
    # Industrials
    "BA", "CAT", "GE", "UNP",
    # Communication services
    "DIS", "NFLX",
]
START = "2015-01-01"
END = "2024-12-31"


def run(strategy_cls, sizer_cls):
    data = DataHandler.from_yfinance(TICKERS, START, END)
    portfolio = Portfolio(data, initial_capital=100_000.0)
    strategy = strategy_cls(data)
    sizer = sizer_cls(data, portfolio)
    broker = SimulatedBroker(data)

    backtest = Backtest(data, strategy, sizer, broker, portfolio, verbose=False)
    result = backtest.run()
    return backtest, broker, result


def report(label: str, backtest: Backtest, broker: SimulatedBroker, result: Portfolio) -> float:
    curve = result.equity_curve()
    final = float(curve["equity"].iloc[-1])
    total_return = final / result.initial_capital - 1.0

    print("-" * 62)
    print(label)
    print("-" * 62)
    print(f"Signals generated       : {backtest.signal_count}")
    print(f"Orders filled           : {backtest.fill_count}")
    print(f"Orders rejected         : {len(broker.rejected)}")
    print(f"Final equity            : {final:>14,.2f}")
    print(f"Total return            : {total_return:>14.2%}")
    print(f"Maximum drawdown        : {curve['drawdown'].min():>14.2%}")
    print(f"Commission + slippage   : {result.total_commission + result.total_slippage:>14,.2f}")
    return total_return


def main() -> None:
    print("\n" + "=" * 62)
    print(f"MOMENTUM vs BUY & HOLD  ({START} -> {END})")
    print(f"Universe ({len(TICKERS)} tickers): {', '.join(TICKERS)}")
    print("=" * 62)

    mom_backtest, mom_broker, mom_result = run(CrossSectionalMomentum, VolatilityTargetSizer)
    mom_return = report(
        "Cross-sectional momentum (12-1) + VolatilityTargetSizer",
        mom_backtest, mom_broker, mom_result,
    )

    bh_backtest, bh_broker, bh_result = run(BuyAndHold, EqualWeightSizer)
    bh_return = report(
        "Buy & hold + EqualWeightSizer",
        bh_backtest, bh_broker, bh_result,
    )

    print("=" * 62)
    print(f"Momentum excess vs buy & hold : {mom_return - bh_return:>10.2%}")
    print("=" * 62)


if __name__ == "__main__":
    main()
