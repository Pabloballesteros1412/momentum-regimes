"""Volatility-scaled momentum (Barroso & Santa-Clara 2015), long-only.

Barroso & Santa-Clara scale the winners-minus-losers portfolio by
target_vol / (its realised volatility over the previous six months).
Momentum's risk is predictable, and its crashes (Daniel & Moskowitz 2016)
come after high-volatility bear markets, so scaling down when recent
volatility is high cuts the crashes.

Long-only analogue used here:

- On each rebalance, the strategy picks the same names as
  CrossSectionalMomentum. It then estimates the annualised volatility of an
  equal-weight portfolio of those names over the previous
  `vol_window` bars (126, about six months), using only past closes. The
  book's **gross exposure** is set to min(target_vol / that vol, max_gross),
  and the rest is held in cash. No leverage by default (max_gross = 1).
- The exposure is carried to the sizer as SignalEvent.strength.
  GrossTargetSizer turns it into a *book-level* gross: it keeps the
  vol-target sizer's relative weights between names, then rescales them so
  their notional is strength × equity. Scaling each name independently
  would be undone by engine v2's cash cap whenever the vol-target weights
  already sum past 100%, which is almost always.

With target_vol large enough that the scale is always capped at 1, this
reduces to a fully invested momentum book (the like-for-like baseline).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from ..engine.events import Direction, MarketEvent, SignalEvent
from ..risk.sizing import VolatilityTargetSizer
from .momentum import CrossSectionalMomentum


class VolScaledMomentum(CrossSectionalMomentum):
    name = "vol_scaled_momentum"

    def __init__(self, data, target_vol: float = 0.20, vol_window: int = 126, max_gross: float = 1.0,
                 **kwargs) -> None:
        super().__init__(data, **kwargs)
        self.target_vol = target_vol
        self.vol_window = vol_window
        self.max_gross = max_gross
        self.scale_log: list[tuple] = []

    def _book_vol(self, symbols: list[str]) -> float | None:
        rets = []
        for s in symbols:
            closes = self.data.get_latest_bars(s, self.vol_window + 1)["close"]
            if len(closes) < self.vol_window // 2:
                continue
            rets.append(closes.pct_change().dropna().rename(s))
        if not rets:
            return None
        ew = pd.concat(rets, axis=1).mean(axis=1, skipna=True).dropna()
        if len(ew) < 20:
            return None
        return float(ew.std() * np.sqrt(252))

    def on_market(self, event: MarketEvent) -> list[SignalEvent]:
        signals = super().on_market(event)
        longs = [s for s in signals if s.direction is Direction.LONG]
        if not longs:
            return signals
        vol = self._book_vol([s.symbol for s in longs])
        scale = self.max_gross if not vol or vol <= 0 else min(self.target_vol / vol, self.max_gross)
        self.scale_log.append((event.timestamp, vol, scale))
        return [replace(s, strength=scale) if s.direction is Direction.LONG else s for s in signals]


class GrossTargetSizer(VolatilityTargetSizer):
    """Engine-v2 vol-target sizer whose long book is rescaled, up *or* down,
    to a gross notional of strength x equity (less the execution buffer).
    Strength is the same for every long in a batch (the strategy's scale).

    Implemented through PositionSizer's full-investment hook: the batch's
    raw vol-target sizes (at strength 1) set the relative weights, and
    _scale_to_full rescales them to the requested gross."""

    def __init__(self, data, portfolio, **kwargs) -> None:
        kwargs["engine_version"] = "v2"
        kwargs["full_investment"] = True
        super().__init__(data, portfolio, **kwargs)
        self._gross: float = 1.0

    def target_quantity(self, signal: SignalEvent) -> int | None:
        return super().target_quantity(replace(signal, strength=1.0))

    def _size_batch_v2(self, signals):
        longs = [s.strength for s in signals if s.direction is Direction.LONG]
        self._gross = max(longs) if longs else 1.0
        return super()._size_batch_v2(signals)

    def _scale_to_full(self, targets):
        prices = {s.symbol: self.data.get_latest_close(s.symbol) for s, t in targets if t > 0}
        notional = sum(t * prices[s.symbol] for s, t in targets if t > 0 and prices[s.symbol])
        if notional <= 0:
            return targets
        factor = self.portfolio.current_equity * (1.0 - self.execution_buffer) * self._gross / notional
        return [(s, int(t * factor) if t > 0 else t) for s, t in targets]
