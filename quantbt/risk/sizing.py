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


ENGINE_VERSIONS = ("v1", "v2")


class PositionSizer(ABC):
    """Base sizer.

    `engine_version` selects how a bar's batch of signals is turned into
    orders (see size_batch):

      - "v1" (default): the published behaviour. Each signal is sized in
        arrival order against cash reserved at the start of the bar. Sell
        proceeds are NOT available to buys in the same batch, so on a
        rebalance day the cash freed by exits sits idle until the next
        rebalance, and when buys exceed cash the alphabetically-later names
        are the ones starved.
      - "v2": exit/trim proceeds are credited to the batch before any buy is
        capped, and if the buys still exceed available cash they are scaled
        down pro rata rather than first-come. The Backtest also settles a
        v2 batch sells-first and trims any buy the account can no longer
        afford at its actual fill (see Backtest._settle_pending), so cash
        can never go negative.

    `full_investment` (v2 only) additionally scales a batch's long targets
    UP so their combined notional is the whole account (less the execution
    buffer), keeping their relative weights. Books already above 100% are
    left to v2's pro-rata cash cap (never scaled down). Vol targeting otherwise holds
    cash by design whenever the names' weights sum to under 100% (e.g. in
    high-volatility markets). This assumes each batch carries the strategy's
    complete target book, as CrossSectionalMomentum's rebalances do; it is
    meaningless for BuyAndHold, whose batches carry only newly listed names.

    The flag lives on the sizer, not the Backtest, so walk-forward and every
    other caller pick it up through their existing sizer_factory with no
    extra plumbing (e.g. functools.partial(VolatilityTargetSizer,
    engine_version="v2")).
    """

    def __init__(
        self, data: DataHandler, portfolio: Portfolio, engine_version: str = "v1", full_investment: bool = False
    ) -> None:
        if engine_version not in ENGINE_VERSIONS:
            raise ValueError(f"engine_version must be one of {ENGINE_VERSIONS}")
        if full_investment and engine_version != "v2":
            raise ValueError("full_investment requires engine_version='v2'")
        self.data = data
        self.portfolio = portfolio
        self.engine_version = engine_version
        self.full_investment = full_investment
        self._reserved_cash: float | None = None

    @abstractmethod
    def target_quantity(self, signal: SignalEvent) -> int | None:
        """Desired end-state position for `signal`, before any cash cap.
        None means "no order" (e.g. not enough history to size)."""
        raise NotImplementedError

    def size(self, signal: SignalEvent) -> OrderEvent | None:
        target = self.target_quantity(signal)
        if target is None:
            return None
        return self._target_to_order(signal, target)

    def size_batch(self, signals: list[SignalEvent]) -> list[OrderEvent]:
        """Turn one bar's signals into orders, according to engine_version."""
        if self.engine_version == "v2":
            return self._size_batch_v2(signals)
        self.begin_batch()
        orders = []
        for signal in signals:
            order = self.size(signal)
            if order is not None:
                orders.append(order)
        return orders

    def _size_batch_v2(self, signals: list[SignalEvent]) -> list[OrderEvent]:
        targets = [(signal, self.target_quantity(signal)) for signal in signals]
        targets = [(signal, t) for signal, t in targets if t is not None]
        if self.full_investment:
            targets = self._scale_to_full(targets)

        sells: list[tuple[SignalEvent, int]] = []
        buys: list[tuple[SignalEvent, int, float]] = []
        for signal, target in targets:
            delta = target - self.portfolio.positions[signal.symbol].quantity
            if delta < 0:
                sells.append((signal, delta))
            elif delta > 0:
                price = self.data.get_latest_close(signal.symbol)
                if price is None or price <= 0:
                    continue
                buys.append((signal, delta, price * (1.0 + self.execution_buffer)))

        # Proceeds are credited at a haircut (same buffer as buys) so an
        # adverse overnight gap on the sells cannot overcommit the buys.
        available = self.portfolio.cash
        for signal, delta in sells:
            price = self.data.get_latest_close(signal.symbol)
            if price is not None and price > 0:
                available += abs(delta) * price * (1.0 - self.execution_buffer)

        cost = sum(delta * worst for _, delta, worst in buys)
        scale = 1.0 if cost <= available or cost <= 0 else max(available, 0.0) / cost

        orders = [self._make_order(signal, delta) for signal, delta in sells]
        for signal, delta, _ in buys:
            quantity = int(delta * scale)
            if quantity > 0:
                orders.append(self._make_order(signal, quantity))
        return orders

    def _scale_to_full(self, targets: list[tuple[SignalEvent, int]]) -> list[tuple[SignalEvent, int]]:
        prices = {signal.symbol: self.data.get_latest_close(signal.symbol) for signal, t in targets if t > 0}
        notional = sum(t * prices[s.symbol] for s, t in targets if t > 0 and prices[s.symbol])
        if notional <= 0:
            return targets
        factor = self.portfolio.current_equity * (1.0 - self.execution_buffer) / notional
        # Scale up only. A book whose weights already sum past 100% is filled
        # by v2's pro-rata cash cap; scaling it *down* to (1 - buffer) here
        # would leave it less invested than plain v2 (the haircuts then bite
        # twice) and churn held positions.
        if factor <= 1.0:
            return targets
        return [(s, int(t * factor) if t > 0 else t) for s, t in targets]

    @staticmethod
    def _make_order(signal: SignalEvent, quantity: int) -> OrderEvent:
        return OrderEvent(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            order_type=OrderType.MARKET,
            quantity=quantity,
        )

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

    def __init__(
        self,
        data: DataHandler,
        portfolio: Portfolio,
        max_leverage: float = 1.0,
        engine_version: str = "v1",
        full_investment: bool = False,
    ) -> None:
        super().__init__(data, portfolio, engine_version, full_investment)
        self.max_leverage = max_leverage

    def target_quantity(self, signal: SignalEvent) -> int | None:
        if signal.direction is Direction.EXIT:
            return 0

        price = self.data.get_latest_close(signal.symbol)
        if price is None or price <= 0:
            return None

        n = max(len(self.data.symbols), 1)
        gross = self.portfolio.current_equity * self.max_leverage / n
        budget = gross * (1.0 - self.execution_buffer)
        return int((budget * signal.strength) / price) * signal.direction.value


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
        engine_version: str = "v1",
        full_investment: bool = False,
    ) -> None:
        super().__init__(data, portfolio, engine_version, full_investment)
        self.target_annual_vol = target_annual_vol
        self.lookback = lookback
        self.max_weight = max_weight

    def target_quantity(self, signal: SignalEvent) -> int | None:
        if signal.direction is Direction.EXIT:
            return 0

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
        return int(budget / price) * signal.direction.value
