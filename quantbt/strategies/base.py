"""Strategy interface.

A strategy sees data and emits SignalEvents. It does not know the portfolio
size, it does not compute share counts, and it never touches cash. Keeping
sizing out of the strategy means the same alpha logic can be run under
different risk budgets without rewriting it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..data.handler import DataHandler
from ..engine.events import MarketEvent, SignalEvent


class Strategy(ABC):
    """Base class for all trading strategies."""

    name: str = "unnamed"

    def __init__(self, data: DataHandler) -> None:
        self.data = data

    @abstractmethod
    def on_market(self, event: MarketEvent) -> list[SignalEvent]:
        """React to a new bar. Return zero or more signals."""
        raise NotImplementedError


class BuyAndHold(Strategy):
    """Equal-weight buy-and-hold. The benchmark every strategy must beat.

    Exists mainly as a pipeline test: if this does not roughly track the
    underlying assets, something in the engine is wrong.
    """

    name = "buy_and_hold"

    def __init__(self, data: DataHandler) -> None:
        super().__init__(data)
        self._invested: set[str] = set()

    def on_market(self, event: MarketEvent) -> list[SignalEvent]:
        from ..engine.events import Direction

        signals: list[SignalEvent] = []
        for symbol in self.data.symbols:
            if symbol in self._invested:
                continue
            if not self.data.has_data(symbol):
                continue

            signals.append(
                SignalEvent(
                    timestamp=event.timestamp,
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=1.0,
                )
            )
            self._invested.add(symbol)

        return signals
