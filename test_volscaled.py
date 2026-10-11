"""Vol-scaled momentum: the book's gross exposure follows the scale.

    python test_volscaled.py
"""

from __future__ import annotations

from functools import partial

from quantbt.data.handler import DataHandler
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.strategies.volscaled import GrossTargetSizer, VolScaledMomentum
from tests.golden_scenarios import synthetic_universe

KW = dict(lookback=126, skip=10, top_decile=0.2)


def _run(target_vol):
    frames = synthetic_universe(n_symbols=20, n_days=900, seed=4)
    data = DataHandler(frames)
    pf = Portfolio(data, initial_capital=100_000.0)
    st = VolScaledMomentum(data, target_vol=target_vol, **KW)
    Backtest(data, st, GrossTargetSizer(data, pf), SimulatedBroker(data), pf).run()
    c = pf.equity_curve()
    return st, c, (c["holdings"] / c["equity"])


def test_gross_follows_scale() -> None:
    st, c, inv = _run(target_vol=0.10)
    scales = [s for _, _, s in st.scale_log]
    assert all(0 < s <= 1.0 for s in scales) and min(scales) < 0.9, scales[:5]
    # A month after each rebalance has settled, invested fraction tracks the scale.
    late = inv.iloc[300:]
    assert late.mean() < 0.9, late.mean()
    assert (c["cash"] >= -1e-6).all()
    print(f"target 10%: mean scale {sum(scales)/len(scales):.2f}, mean invested {late.mean():.2f}; cash never negative")


def test_uncapped_target_is_fully_invested() -> None:
    st, c, inv = _run(target_vol=10.0)
    assert all(s == 1.0 for _, _, s in st.scale_log)
    assert inv.iloc[300:].mean() > 0.93, inv.iloc[300:].mean()
    print(f"target 1000%: scale always 1, mean invested {inv.iloc[300:].mean():.2f}")


if __name__ == "__main__":
    test_gross_follows_scale()
    test_uncapped_target_is_fully_invested()
    print("\nAll vol-scaled momentum tests passed.")
