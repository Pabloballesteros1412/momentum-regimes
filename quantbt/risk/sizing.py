"""Position sizing: the bridge between a signal and an order.

This layer owns every decision about how much capital a signal is worth.
Separating it from the strategy is what lets you run the same alpha under
equal weighting, volatility targeting, or risk parity without touching the
signal code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..data.handler import DataHandler
from ..engine.events import Direction, OrderEvent, OrderType, SignalEvent
from ..portfolio.portfolio import Portfolio


class PositionSizer(ABC):
    def __init__(self, data: DataHandler, portfolio: Portfolio) -> None:
        self.data = data
        self.portfolio = portfolio
        self._reserved_cash: float | None = None

    @abstractmethod
    def size(self, signal: SignalEvent) -> OrderEvent | None:
        raise NotImplementedError

    # Fraction of the notional held back to absorb the gap between the close
    # used for sizing and the next open at which the order actually fills,
    # plus commission. Without it, a favourable overnight gap silently
    # overdraws the account.
    execution_buffer: float = 0.02

    def begin_batch(self) -> None:
        """Reset the cash reservation before sizing a fresh batch of signals.

        Fills settle a bar after the order is created, so portfolio.cash is
        not yet reduced by any order sized earlier in the same batch. Without
        tracking a reservation here, every signal on a multi-symbol rebalance
        day would be checked against the *same*, undiminished cash figure,
        letting the batch collectively commit far more than 100% of the
        account. Call this once per bar, before sizing that bar's signals.
        """
        self._reserved_cash = self.portfolio.cash

    def _target_to_order(self, signal: SignalEvent, target_quantity: int) -> OrderEvent | None:
        """Translate a desired end-state position into an incremental order."""
        current = self.portfolio.positions[signal.symbol].quantity
        delta = target_quantity - current
        if delta == 0:
            return None

        delta = self._cap_by_available_cash(signal.symbol, delta)
        if delta == 0:
            return None

        return OrderEvent(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            order_type=OrderType.MARKET,
            quantity=delta,
        )

    def _cap_by_available_cash(self, symbol: str, quantity: int) -> int:
        """Never submit a buy the account cannot settle at a plausible price."""
        if quantity <= 0:
            return quantity  # sells and shorts release cash rather than consume it

        price = self.data.get_latest_close(symbol)
        if price is None or price <= 0:
            return 0

        worst_case_price = price * (1.0 + self.execution_buffer)
        available = self._reserved_cash if self._reserved_cash is not None else self.portfolio.cash
        affordable = int(available / worst_case_price)
        capped = max(min(quantity, affordable), 0)

        if self._reserved_cash is not None:
            self._reserved_cash -= capped * worst_case_price

        return capped


class EqualWeightSizer(PositionSizer):
    """Allocate an equal fraction of equity to each symbol in the universe."""

    def __init__(self, data: DataHandler, portfolio: Portfolio, max_leverage: float = 1.0) -> None:
        super().__init__(data, portfolio)
        self.max_leverage = max_leverage

    def size(self, signal: SignalEvent) -> OrderEvent | None:
        if signal.direction is Direction.EXIT:
            return self._target_to_order(signal, 0)

        price = self.data.get_latest_close(signal.symbol)
        if price is None or price <= 0:
            return None

        n = max(len(self.data.symbols), 1)
        gross = self.portfolio.current_equity * self.max_leverage / n
        budget = gross * (1.0 - self.execution_buffer)
        target = int((budget * signal.strength) / price) * signal.direction.value
        return self._target_to_order(signal, target)


class VolatilityTargetSizer(PositionSizer):
    """Size each position so its expected volatility contribution is constant.

    A position in a stock realising 60% annualised vol gets a third of the
    capital of one realising 20%. This is the standard fix for a naive
    equal-weight book being dominated by whatever is currently most volatile.
    """

    def __init__(
        self,
        data: DataHandler,
        portfolio: Portfolio,
        target_annual_vol: float = 0.15,
        lookback: int = 60,
        max_weight: float = 0.35,
    ) -> None:
        super().__init__(data, portfolio)
        self.target_annual_vol = target_annual_vol
        self.lookback = lookback
        self.max_weight = max_weight

    def size(self, signal: SignalEvent) -> OrderEvent | None:
        if signal.direction is Direction.EXIT:
            return self._target_to_order(signal, 0)

        bars = self.data.get_latest_bars(signal.symbol, self.lookback + 1)
        if len(bars) < self.lookback // 2:
            return None  # not enough history to estimate risk

        returns = bars["close"].pct_change().dropna()
        realised_vol = float(returns.std()) * np.sqrt(252)
        if realised_vol <= 1e-8:
            return None

        weight = min(self.target_annual_vol / realised_vol, self.max_weight)
        price = float(bars["close"].iloc[-1])
        budget = self.portfolio.current_equity * weight * signal.strength
        target = int(budget / price) * signal.direction.value
        return self._target_to_order(signal, target)
