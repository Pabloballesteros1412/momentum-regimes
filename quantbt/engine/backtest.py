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
from dataclasses import replace

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
            #    Sized as one batch, so a multi-symbol rebalance can't have
            #    every signal size itself against the same undiminished cash
            #    figure (see PositionSizer.size_batch / begin_batch).
            for order in self.sizer.size_batch(signals):
                self._pending_orders.append(order)
                self.order_count += 1

            # 4. Record equity using only prices visible today.
            self.portfolio.mark_to_market(timestamp)

        self._settle_pending()
        return self.portfolio

    def _settle_pending(self) -> None:
        v2 = getattr(self.sizer, "engine_version", "v1") == "v2"
        if v2:
            # Sells first, so their proceeds are in the account before the
            # buys sized against them settle (stable sort keeps the rest of
            # the order intact).
            self._pending_orders = deque(sorted(self._pending_orders, key=lambda o: o.quantity > 0))

        while self._pending_orders:
            order = self._pending_orders.popleft()

            # The broker prices off the NEXT bar, so rewind the clock by one
            # step conceptually: the order was raised on the prior bar.
            fill = self._execute_from_previous_bar(order)
            if fill is not None and v2 and fill.quantity > 0 and fill.total_cost > self.portfolio.cash:
                fill = self._trim_to_cash(order, fill)
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

    def _trim_to_cash(self, order: OrderEvent, fill):
        """v2 only: a buy the account can't afford at its actual fill price
        (a sell got volume-capped, or the open gapped up past the sizing
        haircut) is shrunk until it fits, rather than overdrawing cash."""
        quantity = fill.quantity
        while quantity > 0 and fill is not None and fill.total_cost > self.portfolio.cash:
            per_share = fill.total_cost / fill.quantity
            quantity = min(quantity - 1, int(self.portfolio.cash / per_share))
            if quantity <= 0:
                return None
            fill = self._execute_from_previous_bar(replace(order, quantity=quantity))
        return fill

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
