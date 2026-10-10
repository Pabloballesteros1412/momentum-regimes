"""Point-in-time universe pieces (quantbt/data/universe.py, strategies/pit.py).

    python test_universe.py
"""

from __future__ import annotations

from functools import partial

import pandas as pd

from quantbt.data.handler import DataHandler
from quantbt.data.universe import UniverseSchedule
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.risk.sizing import VolatilityTargetSizer
from quantbt.strategies.momentum import CrossSectionalMomentum
from quantbt.strategies.pit import PITVolatilityTargetSizer, PointInTimeMomentum
from tests.golden_scenarios import synthetic_universe

KW = dict(lookback=126, skip=10, top_decile=0.2)


def _run(frames, strategy, sizer):
    data = DataHandler(frames)
    pf = Portfolio(data, initial_capital=100_000.0)
    st = strategy(data)
    sz = sizer(data, pf)
    Backtest(data, st, sz, SimulatedBroker(data), pf).run()
    return pf, sz


def _always(frames) -> UniverseSchedule:
    return UniverseSchedule(pd.DataFrame([{"ticker": s, "start": "1900-01-01", "end": "2100-01-01"} for s in frames]))


def test_always_member_matches_fixed_universe() -> None:
    frames = synthetic_universe(n_symbols=16, n_days=900, seed=11)
    fixed, _ = _run(frames, partial(CrossSectionalMomentum, **KW), partial(VolatilityTargetSizer, engine_version="v2"))
    pit, _ = _run(frames, partial(PointInTimeMomentum, schedule=_always(frames), **KW),
                  partial(PITVolatilityTargetSizer, engine_version="v2"))
    a, b = fixed.equity_curve(), pit.equity_curve()
    assert a[["cash", "holdings", "equity"]].equals(b[["cash", "holdings", "equity"]])
    print("Always-member schedule reproduces the fixed-universe run exactly.")


def test_never_holds_a_non_member() -> None:
    frames = synthetic_universe(n_symbols=16, n_days=900, seed=11)
    dates = frames["S01"].index
    cut = dates[500]
    iv = [{"ticker": s, "start": "1900-01-01", "end": "2100-01-01"} for s in frames if s not in ("S01", "S02")]
    iv += [{"ticker": "S01", "start": "1900-01-01", "end": cut}, {"ticker": "S02", "start": cut, "end": "2100-01-01"}]
    schedule = UniverseSchedule(pd.DataFrame(iv))
    pf, _ = _run(frames, partial(PointInTimeMomentum, schedule=schedule, **KW),
                 partial(PITVolatilityTargetSizer, engine_version="v2"))
    for f in pf.fills:
        if f.quantity > 0:
            # Buys fill the bar after the signal; the signal day must be a member day.
            signal_day = dates[dates.get_loc(pd.Timestamp(f.timestamp)) - 1]
            assert schedule.is_member(f.symbol, signal_day), (f.symbol, f.timestamp)
    print("No buy is ever signalled on a day its name is not an index member.")


def test_delisted_position_is_liquidated() -> None:
    frames = synthetic_universe(n_symbols=10, n_days=700, seed=2)
    frames = dict(frames)
    always = _always(frames)
    # Find a name the strategy holds around day 450, then end its data there.
    end = frames["S01"].index[450]
    pf, _ = _run({s: df.loc[:end] for s, df in frames.items()}, partial(PointInTimeMomentum, schedule=always, **KW),
                 partial(PITVolatilityTargetSizer, engine_version="v2"))
    held = [s for s, p in pf.positions.items() if p.quantity > 0]
    victim = held[0]
    frames[victim] = frames[victim].loc[:end]
    for dr in (0.0, -0.30):
        pf, sz = _run(frames, partial(PointInTimeMomentum, schedule=always, **KW),
                      partial(PITVolatilityTargetSizer, engine_version="v2", delisting_return=dr))
        assert (end, victim) in sz.liquidations, sz.liquidations
        assert pf.positions[victim].quantity == 0
        assert (pf.equity_curve()["cash"] >= -1e-6).all()
    print(f"A held name whose data ends ({victim}) is liquidated on its last bar, with or without a delisting haircut.")


def test_liquid_variant_restricts_breadth() -> None:
    from quantbt.strategies.pit import PointInTimeLiquidMomentum
    frames = synthetic_universe(n_symbols=16, n_days=900, seed=11)
    pf, _ = _run(frames, partial(PointInTimeLiquidMomentum, schedule=_always(frames), top_n_liquid=5, **KW),
                 partial(PITVolatilityTargetSizer, engine_version="v2"))
    bought = {f.symbol for f in pf.fills if f.quantity > 0}
    wide, _ = _run(frames, partial(PointInTimeLiquidMomentum, schedule=_always(frames), top_n_liquid=100, **KW),
                   partial(PITVolatilityTargetSizer, engine_version="v2"))
    fixed, _ = _run(frames, partial(CrossSectionalMomentum, **KW), partial(VolatilityTargetSizer, engine_version="v2"))
    assert wide.equity_curve()["equity"].equals(fixed.equity_curve()["equity"])
    assert bought and len(bought) < len({f.symbol for f in fixed.fills if f.quantity > 0})
    print("Liquid-subset variant narrows the universe; with no cap it equals the fixed-universe run.")


if __name__ == "__main__":
    test_always_member_matches_fixed_universe()
    test_never_holds_a_non_member()
    test_delisted_position_is_liquidated()
    test_liquid_variant_restricts_breadth()
    print("\nAll universe tests passed.")
