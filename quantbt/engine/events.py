"""Event objects exchanged between engine components.

The engine is a message loop. Components never call each other directly;
they push events onto a queue and react to events they care about. This
keeps the time ordering strict and makes look-ahead bias structurally
impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Direction(Enum):
    LONG = 1
    SHORT = -1
    EXIT = 0


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class MarketEvent:
    """The clock advanced. New bar data is available up to `timestamp`."""

    timestamp: datetime


@dataclass(frozen=True)
class SignalEvent:
    """A strategy expresses desired exposure. It does NOT size the trade."""

    timestamp: datetime
    symbol: str
    direction: Direction
    strength: float = 1.0  # conviction in [0, 1]; risk layer decides size


@dataclass(frozen=True)
class OrderEvent:
    """A concrete, sized instruction sent to the broker."""

    timestamp: datetime
    symbol: str
    order_type: OrderType
    quantity: int  # signed: positive = buy, negative = sell
    limit_price: float | None = None

    def __post_init__(self) -> None:
        if self.quantity == 0:
            raise ValueError("OrderEvent with zero quantity is meaningless")


@dataclass(frozen=True)
class FillEvent:
    """The broker's report of what actually happened."""

    timestamp: datetime
    symbol: str
    quantity: int  # signed
    fill_price: float  # execution price AFTER slippage
    commission: float
    slippage_cost: float  # in currency, vs the reference price

    @property
    def gross_value(self) -> float:
        return self.quantity * self.fill_price

    @property
    def total_cost(self) -> float:
        """Cash impact of the fill, including frictions."""
        return self.gross_value + self.commission
