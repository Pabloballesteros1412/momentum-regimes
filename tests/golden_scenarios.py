"""Deterministic synthetic scenarios shared by the v1 golden-fixture builder
and test_engine_v2.py.

The fixture in tests/fixtures/v1_golden.csv was produced by running these
scenarios on the engine as it stood at commit 1b2ba42, i.e. *before* the
engine-v2 option existed. test_engine_v2.py re-runs them on the current code
with default arguments and requires bit-for-bit equality, so any change that
leaks into the default (v1) path fails loudly.
"""

from __future__ import annotations

import itertools
from functools import partial

import numpy as np
import pandas as pd

from quantbt.data.handler import DataHandler
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from quantbt.strategies.base import BuyAndHold
from quantbt.strategies.momentum import CrossSectionalMomentum, SignalCache
from quantbt.validation.walkforward import run_walkforward


def synthetic_universe(n_symbols: int = 24, n_days: int = 1600, seed: int = 7) -> dict[str, pd.DataFrame]:
    """GBM names with heterogeneous drift/vol, staggered listing dates and
    realistic volume, so momentum rotates and the volume cap can bind."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2010-01-04", periods=n_days, name="timestamp")
    frames = {}
    for i in range(n_symbols):
        mu = rng.normal(0.0004, 0.0004)
        sigma = rng.uniform(0.012, 0.035)
        close = rng.uniform(20, 300) * np.exp(np.cumsum(rng.normal(mu, sigma, n_days)))
        open_ = close * (1 + rng.normal(0, 0.004, n_days))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n_days)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n_days)))
        volume = rng.integers(200_000, 5_000_000, n_days).astype(float)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=dates)
        start = 0 if i % 5 else int(rng.integers(100, 600))  # every 5th name lists late
        frames[f"S{i:02d}"] = df.iloc[start:]
    return frames


def _run(frames, strategy_factory, sizer_factory, capital=100_000.0):
    data = DataHandler(frames)
    portfolio = Portfolio(data, initial_capital=capital)
    strategy = strategy_factory(data)
    sizer = sizer_factory(data, portfolio)
    Backtest(data, strategy, sizer, SimulatedBroker(data), portfolio).run()
    return portfolio.equity_curve()


def run_scenarios(sizer_kwargs: dict | None = None) -> dict[str, pd.DataFrame]:
    """Every scenario's equity curve (cash, holdings, equity columns).

    `sizer_kwargs` is forwarded to every sizer; the golden fixture is built
    and checked with it empty (the default path).
    """
    kw = sizer_kwargs or {}
    frames = synthetic_universe()
    vol_sizer = partial(VolatilityTargetSizer, **kw)
    eq_sizer = partial(EqualWeightSizer, **kw)

    out = {
        "buy_and_hold": _run(frames, BuyAndHold, eq_sizer),
        "momentum_voltarget": _run(frames, partial(CrossSectionalMomentum, lookback=126, skip=10, top_decile=0.2), vol_sizer),
        "momentum_equalweight_quarterly": _run(
            frames, partial(CrossSectionalMomentum, lookback=189, skip=21, top_decile=0.3, rebalance_freq="quarterly"), eq_sizer
        ),
    }

    grid = [
        {"lookback": lb, "skip": sk, "top_decile": f, "rebalance_freq": "monthly"}
        for lb, sk, f in itertools.product([126, 189], [10, 21], [0.1, 0.2])
    ]
    wf = run_walkforward(
        frames=frames,
        param_grid=grid,
        strategy_factory=CrossSectionalMomentum,
        sizer_factory=vol_sizer,
        train_years=2,
        trade_years=1,
        warmup_days=int(189 * 7 / 5) + 30,
        trade_extra_kwargs=lambda trade_start: {"active_from": trade_start},
        strategy_shared_kwargs={"signal_cache": SignalCache.build(frames)},
        n_jobs=1,
    )
    out["walkforward_momentum"] = wf.equity_curve
    return out


def to_long(curves: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, curve in curves.items():
        df = curve[["cash", "holdings", "equity"]].copy()
        df.insert(0, "scenario", name)
        rows.append(df.reset_index())
    return pd.concat(rows, ignore_index=True)
