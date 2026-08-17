"""The event loop.

One pass per bar, always in this order:

    clock advance -> pending fills settle -> strategy sees data
                  -> signals sized into orders -> orders queued for next bar
                  -> mark to market

Fills from orders generated on bar t settle at the START of bar t+1, before
the strategy is allowed to look at bar t+1. That ordering is the whole point:
it guarantees decisions are made only on information that already existed.
"""

from __future__ import annotations

from collections import deque

from ..data.handler import DataHandler
from ..portfolio.portfolio import Portfolio
from ..risk.sizing import PositionSizer
from ..strategies.base import Strategy
from .broker import SimulatedBroker
from .events import MarketEvent, OrderEvent


class Backtest:
    def __init__(
        self,
        data: DataHandler,
        strategy: Strategy,
        sizer: PositionSizer,
        broker: SimulatedBroker,
        portfolio: Portfolio,
        verbose: bool = False,
    ) -> None:
        self.data = data
        self.strategy = strategy
        self.sizer = sizer
        self.broker = broker
        self.portfolio = portfolio
        self.verbose = verbose

        self._pending_orders: deque[OrderEvent] = deque()
        self.signal_count = 0
        self.order_count = 0
        self.fill_count = 0

    def run(self) -> Portfolio:
        while self.data.advance():
            timestamp = self.data.current_time

            # 1. Settle orders raised on the previous bar.
            self._settle_pending()

            # 2. Strategy observes the market as it stands now.
            market = MarketEvent(timestamp=timestamp)
            signals = self.strategy.on_market(market)
            self.signal_count += len(signals)

            # 3. Risk layer turns intent into sized orders for the next bar.
            #    One reservation per bar, so a multi-symbol rebalance can't
            #    have every signal size itself against the same undiminished
            #    cash figure (see PositionSizer.begin_batch).
            self.sizer.begin_batch()
            for signal in signals:
                order = self.sizer.size(signal)
                if order is not None:
                    self._pending_orders.append(order)
                    self.order_count += 1

            # 4. Record equity using only prices visible today.
            self.portfolio.mark_to_market(timestamp)

        self._settle_pending()
        return self.portfolio

    def _settle_pending(self) -> None:
        while self._pending_orders:
            order = self._pending_orders.popleft()

            # The broker prices off the NEXT bar, so rewind the clock by one
            # step conceptually: the order was raised on the prior bar.
            fill = self._execute_from_previous_bar(order)
            if fill is None:
                continue

            self.portfolio.on_fill(fill)
            self.fill_count += 1

            if self.verbose:
                print(
                    f"{fill.timestamp:%Y-%m-%d}  {fill.symbol:<6} "
                    f"{fill.quantity:>+8,d} @ {fill.fill_price:>10,.2f}  "
                    f"comm {fill.commission:>7,.2f}  slip {fill.slippage_cost:>9,.2f}"
                )

    def _execute_from_previous_bar(self, order: OrderEvent):
        """Fill an order at the current bar's open.

        The broker's `get_next_open` is relative to its own cursor, so we step
        the data cursor back one bar for the duration of the call.
        """
        self.data._cursor -= 1
        try:
            return self.broker.execute(order)
        finally:
            self.data._cursor += 1
