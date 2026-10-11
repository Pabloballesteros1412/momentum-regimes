"""Cross-sectional short-term reversal.

Long the *bottom* fraction of the universe by trailing `lookback`-day return
(optionally skipping the most recent `skip` days to limit bid-ask bounce),
rebalanced on the same calendar as momentum. Reversal profits are usually
read as payment for providing liquidity, and are expected to be largest in
high-volatility, stressed markets (Nagel 2012) -- the opposite of where
momentum is weakest.

Implemented as CrossSectionalMomentum with the score negated, so ranking,
rebalance timing, the SignalCache fast path and the fold floor are all
shared code. momentum.py itself is not modified.
"""

from __future__ import annotations

from .momentum import CrossSectionalMomentum


class ShortTermReversal(CrossSectionalMomentum):
    """Long the worst recent performers, monthly rebalance."""

    name = "short_term_reversal"

    def __init__(self, data, lookback: int = 21, skip: int = 0, top_decile: float = 0.1, **kwargs) -> None:
        super().__init__(data, lookback=lookback, skip=skip, top_decile=top_decile, **kwargs)

    def _momentum_score(self, symbol: str) -> float | None:
        score = super()._momentum_score(symbol)
        return None if score is None else -score
