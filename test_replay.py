"""quantbt.validation.replay reproduces run_walkforward exactly.

    python test_replay.py   (or pytest)
"""

from __future__ import annotations

from functools import partial

import pandas as pd

from quantbt.risk.sizing import VolatilityTargetSizer
from quantbt.strategies.momentum import CrossSectionalMomentum
from quantbt.validation.replay import replay_walkforward
from quantbt.validation.walkforward import run_walkforward
from tests.golden_scenarios import synthetic_universe

GRID = [{"lookback": lb, "skip": 10, "top_decile": f, "rebalance_freq": "monthly"} for lb in (63, 126) for f in (0.2, 0.3)]


def test_replay_matches_walkforward() -> None:
    frames = synthetic_universe(n_symbols=14, n_days=1500, seed=9)
    sizer = partial(VolatilityTargetSizer, engine_version="v2")
    wf = run_walkforward(frames, GRID, CrossSectionalMomentum, sizer, train_years=2, trade_years=1,
                         warmup_days=200, trade_extra_kwargs=lambda t: {"active_from": t}, n_jobs=1)
    folds = pd.DataFrame([{"trade_start": f.trade_start, "trade_end": f.trade_end, **f.params} for f in wf.folds])
    r = replay_walkforward(frames, folds, CrossSectionalMomentum, sizer, warmup_days=200)
    assert r.max_equity_gap(wf.equity_curve["equity"]) < 1e-12
    # Holdings are a subset of each rebalance's selection, and positions agree with holdings.
    for d in r.rebalances:
        assert set(r.holdings[d]) <= r.selections[d] | set(r.holdings[d])
        assert all(q > 0 for q in r.holdings[d].values())
    assert set(r.positions.columns) >= {s for h in r.holdings.values() for s in h}
    print(f"replay of {len(wf.folds)} folds matches run_walkforward; {len(r.rebalances)} rebalances recovered")


if __name__ == "__main__":
    test_replay_matches_walkforward()
    print("All replay tests passed.")
