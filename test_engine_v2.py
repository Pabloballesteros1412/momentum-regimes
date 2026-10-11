"""Engine v2 (cash redeployment) tests.

Plain assert-based, run directly: `python test_engine_v2.py`, matching
test_pipeline.py / test_regimes.py.

1. The default path (engine_version="v1") must reproduce the pre-v2 engine
   bit for bit: tests/fixtures/v1_golden.csv was written by the engine at
   commit 1b2ba42, before any v2 code existed (tests/build_v1_golden.py).
2. v2 must keep the book materially more invested, never overdraw cash, and
   still fill every order at the open of the bar after it was raised.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tests.golden_scenarios import run_scenarios, to_long

FIXTURE = Path(__file__).parent / "tests" / "fixtures" / "v1_golden.csv"


def test_default_path_matches_pre_v2_engine() -> None:
    # round_trip: pandas' default fast parser can be off by an ulp, which would
    # make an exact-equality check fail for reasons unrelated to the engine.
    golden = pd.read_csv(FIXTURE, parse_dates=["timestamp"], float_precision="round_trip")
    current = to_long(run_scenarios())
    current["timestamp"] = pd.to_datetime(current["timestamp"])
    assert list(golden.columns) == list(current.columns)
    assert len(golden) == len(current), f"row count changed: {len(golden)} -> {len(current)}"
    for col in golden.columns:
        g, c = golden[col], current[col]
        if col in ("cash", "holdings", "equity"):
            # Exact float equality: %.17g round-trips every double.
            bad = (g.to_numpy() != c.to_numpy())
        else:
            bad = (g.astype(str).to_numpy() != c.astype(str).to_numpy())
        assert not bad.any(), f"default path diverged from pre-v2 engine in '{col}' at {int(bad.sum())} rows"
    print(f"Default (v1) path matches the pre-v2 engine exactly ({len(golden):,} rows, 4 scenarios).")


def test_v2_is_invested_and_solvent() -> None:
    v1 = run_scenarios()
    v2 = run_scenarios({"engine_version": "v2"})
    for name in v1:
        c1, c2 = v1[name], v2[name]
        assert (c2["cash"] >= -1e-6).all(), f"{name}: v2 overdrew cash (min {c2['cash'].min():,.2f})"
        inv1 = (c1["holdings"] / c1["equity"]).iloc[300:]
        inv2 = (c2["holdings"] / c2["equity"]).iloc[300:]
        print(f"  {name:<32} invested fraction  v1 mean {inv1.mean():.3f} min {inv1.min():.3f}"
              f"   v2 mean {inv2.mean():.3f} min {inv2.min():.3f}")
        assert inv2.mean() >= inv1.mean() - 1e-3, f"{name}: v2 lowered the invested fraction"
        # Vol-target momentum is the published configuration and the one the
        # idle-exit-cash bug hits. EqualWeightSizer under momentum is capped
        # far below 100% by design (1/N of the *whole* universe per name),
        # so v2 has nothing to redeploy there.
        if name in ("momentum_voltarget", "walkforward_momentum"):
            assert inv2.mean() > inv1.mean() + 0.05, f"{name}: v2 did not materially raise the invested fraction"
    print("v2 raises the invested fraction of rotating strategies and never overdraws cash.")


def test_v2_full_investment() -> None:
    """full_investment rescales vol-target weights to ~100% gross, and is
    rejected outside v2."""
    from functools import partial

    from quantbt.risk.sizing import VolatilityTargetSizer
    from tests.golden_scenarios import _run, synthetic_universe
    from quantbt.strategies.momentum import CrossSectionalMomentum

    frames = synthetic_universe()
    # top_decile=0.1 of 24 names = 2 holdings, at most 2 x 35% = 70% under
    # plain vol targeting: the case where only full_investment can fill it.
    strat = partial(CrossSectionalMomentum, lookback=126, skip=10, top_decile=0.1)
    curves = {
        v: _run(frames, strat, partial(VolatilityTargetSizer, **kw))
        for v, kw in {"v2": {"engine_version": "v2"},
                      "v2full": {"engine_version": "v2", "full_investment": True}}.items()
    }
    inv = {v: (c["holdings"] / c["equity"]).iloc[300:] for v, c in curves.items()}
    print(f"  2-name book: v2 mean {inv['v2'].mean():.3f}, v2full mean {inv['v2full'].mean():.3f} "
          f"(min {inv['v2full'].min():.3f})")
    assert inv["v2"].mean() < 0.75
    assert inv["v2full"].mean() > 0.95
    assert (curves["v2full"]["cash"] >= -1e-6).all()
    try:
        VolatilityTargetSizer(None, None, full_investment=True)
    except ValueError:
        pass
    else:
        raise AssertionError("full_investment must require engine_version='v2'")
    print("full_investment fills the book to ~100% and is v2-only.")


def test_v2_fills_next_bar_only() -> None:
    """Orders raised on bar t must still fill on bar t+1 under v2."""
    from functools import partial

    from quantbt.data.handler import DataHandler
    from quantbt.engine.backtest import Backtest
    from quantbt.engine.broker import SimulatedBroker
    from quantbt.portfolio.portfolio import Portfolio
    from quantbt.risk.sizing import VolatilityTargetSizer
    from quantbt.strategies.momentum import CrossSectionalMomentum
    from tests.golden_scenarios import synthetic_universe

    frames = synthetic_universe()
    data = DataHandler(frames)
    portfolio = Portfolio(data, 100_000.0)
    strategy = CrossSectionalMomentum(data, lookback=126, skip=10, top_decile=0.2)
    raised: dict = {}
    original = strategy.on_market

    def spy(event):
        signals = original(event)
        for s in signals:
            raised.setdefault(s.symbol, []).append(event.timestamp)
        return signals

    strategy.on_market = spy
    sizer = partial(VolatilityTargetSizer, engine_version="v2")(data, portfolio)
    Backtest(data, strategy, sizer, SimulatedBroker(data), portfolio).run()
    timeline = data.timeline
    for fill in portfolio.fills:
        prev = timeline[timeline.get_loc(pd.Timestamp(fill.timestamp)) - 1]
        assert prev in raised.get(fill.symbol, []), f"{fill.symbol} filled {fill.timestamp} without a signal on {prev}"
    print(f"All {len(portfolio.fills):,} v2 fills settle on the bar after their signal.")


if __name__ == "__main__":
    test_default_path_matches_pre_v2_engine()
    test_v2_is_invested_and_solvent()
    test_v2_full_investment()
    test_v2_fills_next_bar_only()
    print("\nAll engine v2 tests passed.")
