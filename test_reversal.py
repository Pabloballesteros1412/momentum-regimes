"""ShortTermReversal selects recent losers, and is exactly momentum with the
sign flipped.

    python test_reversal.py
"""

from __future__ import annotations

import numpy as np

from quantbt.data.handler import DataHandler
from quantbt.engine.events import Direction, MarketEvent
from quantbt.strategies.momentum import CrossSectionalMomentum, SignalCache
from quantbt.strategies.reversal import ShortTermReversal
from tests.golden_scenarios import synthetic_universe


def _signals_on_last_bar(strategy_cls, frames, **kwargs):
    data = DataHandler(frames)
    strategy = strategy_cls(data, **kwargs)
    while data.advance():
        if data.current_time == data.timeline[-1]:
            strategy._current_period = None  # force a rebalance on the final bar
        signals = strategy.on_market(MarketEvent(timestamp=data.current_time))
    return {s.symbol for s in signals if s.direction is Direction.LONG}


def test_selects_the_crashed_name() -> None:
    frames = synthetic_universe(n_symbols=10, n_days=300, seed=3)
    frames = {s: df.copy() for s, df in frames.items()}
    # Crash S01 by 40% over the final 10 days.
    df = frames["S01"]
    df.iloc[-10:, df.columns.get_loc("close")] *= np.linspace(0.95, 0.6, 10)
    picks = _signals_on_last_bar(ShortTermReversal, frames, lookback=10, skip=0, top_decile=0.1)
    assert picks == {"S01"}, picks
    print(f"Reversal picks the crashed name: {sorted(picks)}")


def test_sign_flip_equals_momentum() -> None:
    frames = synthetic_universe(n_symbols=20, n_days=400, seed=5)
    cache = SignalCache.build(frames)
    for lookback, skip in [(5, 0), (21, 1)]:
        rev = _signals_on_last_bar(ShortTermReversal, frames, lookback=lookback, skip=skip, top_decile=0.2,
                                   signal_cache=cache)

        class Flipped(ShortTermReversal):
            def _momentum_score(self, symbol):
                s = super()._momentum_score(symbol)
                return None if s is None else -s

        mom = _signals_on_last_bar(CrossSectionalMomentum, frames, lookback=lookback, skip=skip, top_decile=0.2)
        flipped = _signals_on_last_bar(Flipped, frames, lookback=lookback, skip=skip, top_decile=0.2)
        assert flipped == mom, (flipped, mom)
        assert rev.isdisjoint(mom), (rev, mom)
    print("Reversal with its sign flipped back selects exactly momentum's names (cache and no-cache paths).")


if __name__ == "__main__":
    test_selects_the_crashed_name()
    test_sign_flip_equals_momentum()
    print("\nAll reversal tests passed.")
