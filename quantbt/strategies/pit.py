"""Point-in-time variants for a survivorship-bias check (PLAN.md item 1).

All opt-in; nothing here changes the default engine path.

- PointInTimeMomentum: CrossSectionalMomentum that only ranks names that
  are index members on the rebalance day. A held name that leaves the index
  is exited at the next rebalance, like any name that drops out of the top.
- PointInTimeEqualWeight: the benchmark. Equal weight across current
  members (with a price), rebalanced monthly. BuyAndHold can't be used: it
  would accumulate every name that ever joined and never sell.
- Sizers with end-of-data liquidation: a held name whose price history ends
  (delisted, acquired, or simply not in the free data any more) would
  otherwise stay marked at its last close forever, unsellable, because the
  broker needs a next-bar open. On the name's last bar, these sizers sell
  the position at that close times (1 + delisting_return) and credit cash.
  This sees one bar ahead (that tomorrow has no bar) -- the usual
  "liquidate at the last price" convention. delisting_return=-0.30 is the
  Shumway (1997) assumption for performance-related delistings.
"""

from __future__ import annotations

from ..data.universe import UniverseSchedule
from ..engine.events import Direction, FillEvent, MarketEvent, SignalEvent
from ..risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from .base import Strategy
from .momentum import CrossSectionalMomentum


class PointInTimeMomentum(CrossSectionalMomentum):
    name = "pit_momentum"

    def __init__(self, data, schedule: UniverseSchedule, **kwargs) -> None:
        super().__init__(data, **kwargs)
        self.schedule = schedule

    def _momentum_score(self, symbol: str) -> float | None:
        if not self.schedule.is_member(symbol, self.data.current_time):
            return None
        return super()._momentum_score(symbol)


class PointInTimeEqualWeight(Strategy):
    name = "pit_equal_weight"

    def __init__(self, data, schedule: UniverseSchedule, active_from=None, **_) -> None:
        super().__init__(data)
        self.schedule = schedule
        self.active_from = active_from
        self._period = None
        self._held: set[str] = set()
        self.n_members = 1

    def on_market(self, event: MarketEvent) -> list[SignalEvent]:
        """On the first bar of each month, target equal weight across members with a bar today."""
        if self.active_from is not None and event.timestamp < self.active_from:
            return []
        period = (event.timestamp.year, event.timestamp.month)
        if period == self._period:
            return []
        self._period = period
        ts = self.data.current_time
        today = self.data.timeline[self.data._cursor]
        # Members with a bar today (a name without one can't be priced or traded).
        members = {s for s in self.data.symbols
                   if self.schedule.is_member(s, ts) and today in self.data._frames[s].index}
        self.n_members = max(len(members), 1)
        signals = [SignalEvent(timestamp=event.timestamp, symbol=s, direction=Direction.EXIT)
                   for s in sorted(self._held - members)]
        signals += [SignalEvent(timestamp=event.timestamp, symbol=s, direction=Direction.LONG)
                    for s in sorted(members)]
        self._held = members
        return signals


class _LiquidateOnEndOfData:
    """Mixin: sells held names on their last available bar (see module doc)."""

    delisting_return: float = 0.0

    def size_batch(self, signals: list[SignalEvent]) -> list:
        """Liquidate names whose data ended today, then size the batch as usual."""
        self._liquidate_ended()
        return super().size_batch(signals)

    def _liquidate_ended(self) -> None:
        data, pf = self.data, self.portfolio
        cursor = data._cursor
        if cursor + 1 >= len(data.timeline):
            return  # the dataset's own last bar is not a delisting
        today, tomorrow = data.timeline[cursor], data.timeline[cursor + 1]
        for symbol, pos in pf.positions.items():
            if pos.quantity == 0:
                continue
            frame = data._frames[symbol]
            if frame.index[-1] != today:
                continue
            price = float(frame["close"].iloc[-1]) * (1.0 + self.delisting_return)
            fill = FillEvent(timestamp=tomorrow.to_pydatetime(), symbol=symbol, quantity=-pos.quantity,
                             fill_price=price, commission=0.0, slippage_cost=0.0)
            pf.on_fill(fill)
            self.liquidations.append((today, symbol))


class PITVolatilityTargetSizer(_LiquidateOnEndOfData, VolatilityTargetSizer):
    def __init__(self, data, portfolio, delisting_return: float = 0.0, **kwargs) -> None:
        super().__init__(data, portfolio, **kwargs)
        self.delisting_return = delisting_return
        self.liquidations: list = []


class PITEqualWeightSizer(_LiquidateOnEndOfData, EqualWeightSizer):
    """Equal weight over the strategy's current member count, not over every
    symbol the DataHandler holds (which is every name that was ever a member)."""

    def __init__(self, data, portfolio, delisting_return: float = 0.0, **kwargs) -> None:
        super().__init__(data, portfolio, **kwargs)
        self.delisting_return = delisting_return
        self.liquidations: list = []
        self.strategy: PointInTimeEqualWeight | None = None

    def target_quantity(self, signal: SignalEvent) -> int | None:
        """Equal share of equity per current member (1 / strategy.n_members)."""
        if signal.direction is Direction.EXIT:
            return 0
        price = self.data.get_latest_close(signal.symbol)
        if price is None or price <= 0:
            return None
        n = self.strategy.n_members if self.strategy is not None else 1
        budget = self.portfolio.current_equity * self.max_leverage / n * (1.0 - self.execution_buffer)
        return int(budget / price)


class PointInTimeLiquidMomentum(PointInTimeMomentum):
    """PointInTimeMomentum restricted, on each rebalance day, to the
    `top_n_liquid` current members by trailing average dollar volume.

    A breadth control: the fixed-universe study ranks ~37 large names, the
    PIT S&P 500 ranks ~500. This keeps the universe point-in-time but about
    as narrow as the fixed list, so survivorship and breadth can be told
    apart (PLAN.md item 1, "Risks")."""

    name = "pit_liquid_momentum"

    def __init__(self, data, schedule: UniverseSchedule, top_n_liquid: int = 40, liquidity_window: int = 63,
                 **kwargs) -> None:
        super().__init__(data, schedule, **kwargs)
        self.top_n_liquid = top_n_liquid
        self.liquidity_window = liquidity_window
        self._liquid_at = None
        self._liquid: set[str] = set()

    def _momentum_score(self, symbol: str) -> float | None:
        now = self.data.current_time
        if self._liquid_at != now:
            self._liquid_at = now
            dollar_volume = {}
            for s in self.data.symbols:
                if not self.schedule.is_member(s, now):
                    continue
                bars = self.data.get_latest_bars(s, self.liquidity_window)
                if len(bars) and bars.index[-1] == self.data.timeline[self.data._cursor]:
                    dollar_volume[s] = float((bars["close"] * bars["volume"]).mean())
            self._liquid = set(sorted(dollar_volume, key=dollar_volume.get, reverse=True)[: self.top_n_liquid])
        if symbol not in self._liquid:
            return None
        return super()._momentum_score(symbol)
