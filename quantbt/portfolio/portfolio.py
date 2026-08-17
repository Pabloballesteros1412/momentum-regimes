"""Position and cash bookkeeping, plus the equity curve.

The portfolio is the only component allowed to mutate cash and positions,
and it does so exclusively in response to FillEvents. Nothing updates the
book on a signal or an order, because neither of those is a transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from ..data.handler import DataHandler
from ..engine.events import FillEvent


@dataclass
class Position:
    symbol: str
    quantity: int = 0
    average_cost: float = 0.0
    realised_pnl: float = 0.0

    def apply_fill(self, fill: FillEvent) -> None:
        new_quantity = self.quantity + fill.quantity

        # Adding to an existing position (or opening one): blend the cost basis.
        if self.quantity == 0 or (self.quantity > 0) == (fill.quantity > 0):
            total_cost = self.average_cost * abs(self.quantity) + fill.fill_price * abs(fill.quantity)
            self.average_cost = total_cost / abs(new_quantity) if new_quantity else 0.0
        else:
            # Reducing or flipping: crystallise P&L on the closed portion.
            closed = min(abs(fill.quantity), abs(self.quantity))
            direction = 1 if self.quantity > 0 else -1
            self.realised_pnl += direction * closed * (fill.fill_price - self.average_cost)

            if abs(fill.quantity) > abs(self.quantity):
                self.average_cost = fill.fill_price  # position flipped
            elif new_quantity == 0:
                self.average_cost = 0.0

        self.quantity = new_quantity

    def market_value(self, price: float) -> float:
        return self.quantity * price

    def unrealised_pnl(self, price: float) -> float:
        if self.quantity == 0:
            return 0.0
        return self.quantity * (price - self.average_cost)


@dataclass
class Portfolio:
    data: DataHandler
    initial_capital: float = 100_000.0

    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict, init=False)
    history: list[dict] = field(default_factory=list, init=False)
    fills: list[FillEvent] = field(default_factory=list, init=False)
    total_commission: float = field(default=0.0, init=False)
    total_slippage: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.cash = self.initial_capital
        self.positions = {sym: Position(sym) for sym in self.data.symbols}

    # ------------------------------------------------------------------
    def on_fill(self, fill: FillEvent) -> None:
        self.cash -= fill.total_cost
        self.positions[fill.symbol].apply_fill(fill)
        self.fills.append(fill)
        self.total_commission += fill.commission
        self.total_slippage += fill.slippage_cost

    def mark_to_market(self, timestamp: datetime) -> None:
        """Snapshot total equity using the latest observable closes."""
        holdings_value = 0.0
        for symbol, position in self.positions.items():
            if position.quantity == 0:
                continue
            price = self.data.get_latest_close(symbol)
            if price is not None:
                holdings_value += position.market_value(price)

        self.history.append(
            {
                "timestamp": timestamp,
                "cash": self.cash,
                "holdings": holdings_value,
                "equity": self.cash + holdings_value,
            }
        )

    # ------------------------------------------------------------------
    @property
    def current_equity(self) -> float:
        if not self.history:
            return self.initial_capital
        return float(self.history[-1]["equity"])

    def equity_curve(self) -> pd.DataFrame:
        if not self.history:
            raise RuntimeError("Portfolio has no recorded history")
        curve = pd.DataFrame(self.history).set_index("timestamp")
        curve["returns"] = curve["equity"].pct_change().fillna(0.0)
        curve["cumulative"] = (1.0 + curve["returns"]).cumprod()
        curve["drawdown"] = curve["cumulative"] / curve["cumulative"].cummax() - 1.0
        return curve
