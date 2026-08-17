"""Real-data run of the buy-and-hold pipeline against five large S&P 500 names,
benchmarked against SPY over the same period.
"""

from __future__ import annotations

from quantbt.data.handler import DataHandler
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.risk.sizing import EqualWeightSizer
from quantbt.strategies.base import BuyAndHold

TICKERS = ["AAPL", "MSFT", "AMZN", "GOOGL", "JPM"]
START = "2015-01-01"
END = "2024-12-31"


def buy_and_hold_return(symbol: str, start: str, end: str) -> float:
    """Frictionless buy-and-hold return for a single symbol.

    Enters at the open of the *second* bar, mirroring the one-bar fill delay
    the engine itself imposes (a signal on bar t fills at the open of bar
    t+1), so this is comparable to the engine's own total_return.
    """
    dh = DataHandler.from_yfinance([symbol], start, end)
    dh.advance()
    dh.advance()
    entry_open = float(dh.get_latest_bars(symbol, 1)["open"].iloc[0])
    while dh.advance():
        pass
    exit_close = dh.get_latest_close(symbol)
    return exit_close / entry_open - 1.0


def main() -> None:
    data = DataHandler.from_yfinance(TICKERS, START, END)

    portfolio = Portfolio(data, initial_capital=100_000.0)
    strategy = BuyAndHold(data)
    sizer = EqualWeightSizer(data, portfolio)
    broker = SimulatedBroker(data)

    backtest = Backtest(data, strategy, sizer, broker, portfolio, verbose=False)
    result = backtest.run()

    curve = result.equity_curve()
    final = float(curve["equity"].iloc[-1])
    total_return = final / result.initial_capital - 1.0

    spy_return = buy_and_hold_return("SPY", START, END)

    print("\n" + "=" * 62)
    print(f"REAL-DATA BUY & HOLD  ({START} -> {END})")
    print("=" * 62)
    print(f"Universe                : {', '.join(TICKERS)}")
    print(f"Signals generated       : {backtest.signal_count}")
    print(f"Orders filled           : {backtest.fill_count}")
    print(f"Orders rejected         : {len(broker.rejected)}")
    print("-" * 62)
    print(f"Initial capital         : {result.initial_capital:>14,.2f}")
    print(f"Final equity            : {final:>14,.2f}")
    print(f"Portfolio total return  : {total_return:>14.2%}")
    print(f"SPY buy & hold return   : {spy_return:>14.2%}")
    print(f"Excess vs SPY           : {total_return - spy_return:>14.2%}")
    print("-" * 62)
    print(f"Total commission paid   : {result.total_commission:>14,.2f}")
    print(f"Total slippage cost     : {result.total_slippage:>14,.2f}")
    print(f"Maximum drawdown        : {curve['drawdown'].min():>14.2%}")
    print(f"Residual cash           : {result.cash:>14,.2f}")
    print("=" * 62)


if __name__ == "__main__":
    main()
