"""Execution simulation: turns orders into fills, charging realistic frictions.

Three frictions are modelled:

  1. Delay      - an order created on bar t executes at the open of bar t+1.
  2. Slippage   - the fill price is worse than the reference price, scaled by
                  the order's size relative to typical volume.
  3. Commission - a per-share fee with a per-order minimum.

Ignoring these is the single most common reason a backtest looks profitable
and a live account does not.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..data.handler import DataHandler
from .events import FillEvent, OrderEvent


@dataclass
class CommissionModel:
    """Interactive-Brokers-style tiered retail pricing."""

    per_share: float = 0.005
    minimum: float = 1.00
    max_pct_of_trade: float = 0.01

    def calculate(self, quantity: int, price: float) -> float:
        raw = abs(quantity) * self.per_share
        capped = min(max(raw, self.minimum), abs(quantity) * price * self.max_pct_of_trade)
        return round(capped, 4)


@dataclass
class SlippageModel:
    """Square-root market impact plus a fixed spread cost.

    Impact grows with the square root of participation rate, which is the
    standard empirical result: doubling your order size does not double the
    price you push the market by.
    """

    spread_bps: float = 2.0
    impact_coefficient: float = 10.0

    def calculate(self, quantity: int, price: float, avg_volume: float) -> float:
        """Return the per-share price penalty, always adverse to the trader."""
        spread_cost = price * (self.spread_bps / 10_000.0)

        if avg_volume <= 0:
            participation = 0.0
        else:
            participation = min(abs(quantity) / avg_volume, 1.0)

        impact = price * (self.impact_coefficient / 10_000.0) * (participation ** 0.5)
        return spread_cost + impact


class SimulatedBroker:
    """Executes orders against next-bar data with frictions applied."""

    def __init__(
        self,
        data: DataHandler,
        commission: CommissionModel | None = None,
        slippage: SlippageModel | None = None,
        max_participation: float = 0.10,
    ) -> None:
        self.data = data
        self.commission = commission or CommissionModel()
        self.slippage = slippage or SlippageModel()
        self.max_participation = max_participation
        self.rejected: list[tuple[OrderEvent, str]] = []

    def execute(self, order: OrderEvent) -> FillEvent | None:
        """Attempt to fill an order. Returns None if the order cannot execute."""
        reference_price = self.data.get_next_open(order.symbol)
        if reference_price is None or reference_price <= 0:
            self.rejected.append((order, "no next-bar price available"))
            return None

        bars = self.data.get_latest_bars(order.symbol, 20)
        avg_volume = float(bars["volume"].mean()) if not bars.empty else 0.0

        quantity = self._apply_volume_cap(order, avg_volume)
        if quantity == 0:
            self.rejected.append((order, "size below tradable minimum after volume cap"))
            return None

        per_share_slippage = self.slippage.calculate(quantity, reference_price, avg_volume)

        # Slippage always works against the trader: buys fill higher, sells lower.
        sign = 1 if quantity > 0 else -1
        fill_price = reference_price + sign * per_share_slippage

        commission = self.commission.calculate(quantity, fill_price)
        slippage_cost = abs(quantity) * per_share_slippage

        # The fill is stamped with the timestamp of the bar it executed on.
        fill_time = self.data.timeline[self.data.timeline.get_loc(self.data.current_time) + 1]

        return FillEvent(
            timestamp=fill_time.to_pydatetime(),
            symbol=order.symbol,
            quantity=quantity,
            fill_price=round(fill_price, 6),
            commission=commission,
            slippage_cost=round(slippage_cost, 6),
        )

    def _apply_volume_cap(self, order: OrderEvent, avg_volume: float) -> int:
        """Refuse to pretend we can trade more than a slice of daily volume."""
        if avg_volume <= 0:
            return 0
        cap = int(avg_volume * self.max_participation)
        if cap == 0:
            return 0
        sign = 1 if order.quantity > 0 else -1
        return sign * min(abs(order.quantity), cap)
