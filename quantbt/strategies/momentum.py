"""Cross-sectional 12-1 momentum.

Classic academic momentum: rank the universe by trailing 252-trading-day
return, but drop the most recent 21 days from that window. The exclusion
matters because the most recent month tends to mean-revert (short-term
reversal), which would otherwise contaminate a pure momentum signal.

Rebalancing happens on a fixed calendar cadence -- monthly or quarterly --
on the first bar the strategy sees in a new period. Between rebalances the
strategy is silent: it neither resizes existing winners nor reacts to
daily moves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from ..data.handler import DataHandler
from ..engine.events import Direction, MarketEvent, SignalEvent
from .base import Strategy


@dataclass
class SignalCache:
    """Precomputed close-price arrays for O(1) momentum lookups.

    A walk-forward grid search runs many CrossSectionalMomentum instances
    -- one per parameter combination, every fold -- against the *same*
    underlying price history. Without this, each one independently repeats
    DataHandler.get_latest_bars()'s label-based slicing on every rebalance,
    for every symbol, from scratch. Build this once per universe (the raw
    frames a DataHandler would otherwise hold), share it across every
    combination and fold, and _momentum_score becomes two array lookups.

    Semantics are identical to get_latest_bars(symbol, lookback) followed
    by closes.iloc[0] / closes.iloc[-(skip+1)]: positions are relative to
    that symbol's *own* observed trading days, not a shared calendar, so
    this changes performance only, never a strategy's behavior.

    Built once from a universe's *full* history, this cache has no notion
    of a walk-forward fold's boundaries on its own -- a fold's training
    DataHandler only ever holds that fold's own sliced frames, but this
    cache's arrays span the whole universe. Every lookup therefore takes an
    explicit `floor` position and refuses to reach earlier than it; callers
    derive that floor from whatever DataHandler they were actually given
    (see CrossSectionalMomentum.__init__), so a training run can never see
    data an unbounded cache would otherwise dangle in front of it.
    """

    close: dict[str, np.ndarray] = field(default_factory=dict)
    position: dict[str, dict[pd.Timestamp, int]] = field(default_factory=dict)

    @classmethod
    def build(cls, frames: dict[str, pd.DataFrame]) -> "SignalCache":
        close: dict[str, np.ndarray] = {}
        position: dict[str, dict[pd.Timestamp, int]] = {}
        for symbol, df in frames.items():
            df = df.sort_index()
            close[symbol] = df["close"].to_numpy(dtype=float)
            position[symbol] = {ts: i for i, ts in enumerate(df.index)}
        return cls(close=close, position=position)

    def floor_position(self, symbol: str, earliest_visible_date) -> int:
        """The array position a caller may not look before, for `symbol`."""
        pos_map = self.position.get(symbol)
        if pos_map is None:
            return 0
        return pos_map.get(earliest_visible_date, 0)

    def momentum_score(
        self, symbol: str, current_time, lookback: int, skip: int, floor: int = 0
    ) -> float | None:
        pos_map = self.position.get(symbol)
        if pos_map is None:
            return None
        pos = pos_map.get(current_time)
        if pos is None or pos - lookback + 1 < floor:
            return None

        closes = self.close[symbol]
        start_price = float(closes[pos - lookback + 1])
        recent_price = float(closes[pos - skip])
        if start_price <= 0:
            return None
        return recent_price / start_price - 1.0


class CrossSectionalMomentum(Strategy):
    """Long the top decile of trailing 12-1 momentum, monthly rebalance."""

    name = "cross_sectional_momentum"

    REBALANCE_FREQUENCIES = ("monthly", "quarterly")

    def __init__(
        self,
        data: DataHandler,
        lookback: int = 252,
        skip: int = 21,
        top_decile: float = 0.1,
        rebalance_freq: str = "monthly",
        active_from: datetime | None = None,
        signal_cache: SignalCache | None = None,
    ) -> None:
        super().__init__(data)
        if rebalance_freq not in self.REBALANCE_FREQUENCIES:
            raise ValueError(f"rebalance_freq must be one of {self.REBALANCE_FREQUENCIES}")

        self.lookback = lookback
        self.skip = skip
        self.top_decile = top_decile
        self.rebalance_freq = rebalance_freq
        # Lets a caller feed bars from before this date purely to warm up
        # the lookback window (e.g. a walk-forward trading window) without
        # the strategy actually trading on them.
        self.active_from = active_from
        # Optional fast path -- see SignalCache's docstring. Falls back to
        # DataHandler.get_latest_bars() when not given. The floor is derived
        # from this specific DataHandler's own frames (whatever fold-local
        # or warmup-extended slice it was built from), so the cache can span
        # the whole universe without ever handing this instance data from
        # before what it was actually given.
        self.signal_cache = signal_cache
        self._floor_position: dict[str, int] = {}
        if signal_cache is not None:
            self._floor_position = {
                symbol: signal_cache.floor_position(symbol, frame.index.min())
                for symbol, frame in data.frames.items()
            }

        self._current_period: tuple[int, int] | None = None
        self._held: set[str] = set()

    def on_market(self, event: MarketEvent) -> list[SignalEvent]:
        if self.active_from is not None and event.timestamp < self.active_from:
            return []
        if not self._is_rebalance_day(event.timestamp):
            return []

        scores = {
            symbol: score
            for symbol in self.data.symbols
            if (score := self._momentum_score(symbol)) is not None
        }
        if not scores:
            return []

        ranked = sorted(scores, key=scores.get, reverse=True)
        n_top = max(1, round(len(ranked) * self.top_decile))
        top = set(ranked[:n_top])

        signals: list[SignalEvent] = []

        # Names that dropped out of the top decile since the last rebalance.
        for symbol in sorted(self._held - top):
            signals.append(
                SignalEvent(
                    timestamp=event.timestamp,
                    symbol=symbol,
                    direction=Direction.EXIT,
                )
            )

        # Current top decile, whether newly entered or held over.
        for symbol in sorted(top):
            signals.append(
                SignalEvent(
                    timestamp=event.timestamp,
                    symbol=symbol,
                    direction=Direction.LONG,
                )
            )

        self._held = top
        return signals

    def _is_rebalance_day(self, timestamp: datetime) -> bool:
        """True on the first bar of each new rebalance period."""
        if self.rebalance_freq == "quarterly":
            period_key = (timestamp.year, (timestamp.month - 1) // 3)
        else:
            period_key = (timestamp.year, timestamp.month)

        if period_key == self._current_period:
            return False
        self._current_period = period_key
        return True

    def _momentum_score(self, symbol: str) -> float | None:
        """Trailing 12-1 return, or None if there isn't a full window yet."""
        if self.signal_cache is not None:
            floor = self._floor_position.get(symbol, 0)
            return self.signal_cache.momentum_score(
                symbol, self.data.current_time, self.lookback, self.skip, floor=floor
            )

        bars = self.data.get_latest_bars(symbol, self.lookback)
        if len(bars) < self.lookback:
            return None

        closes = bars["close"]
        start_price = float(closes.iloc[0])
        recent_price = float(closes.iloc[-(self.skip + 1)])
        if start_price <= 0:
            return None

        return recent_price / start_price - 1.0
