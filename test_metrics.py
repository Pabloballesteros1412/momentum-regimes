"""quantbt.analytics.metrics on series whose answers are known by hand.

    python test_metrics.py   (or pytest)
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from quantbt.analytics import metrics as m

IDX = pd.bdate_range("2020-01-01", periods=6)


def test_cagr_and_total_growth() -> None:
    r = pd.Series([0.01] * 252, index=pd.bdate_range("2020-01-01", periods=252))
    assert abs(m.cagr(r) - (1.01 ** 252 - 1)) < 1e-12
    assert m.cagr(pd.Series([-1.0, 0.1], index=IDX[:2])) == -1.0  # wiped out
    assert math.isnan(m.cagr(pd.Series(dtype=float)))


def test_drawdown_and_duration() -> None:
    r = pd.Series([0.10, -0.50, 0.20, 1.00, 0.0, 0.0], index=IDX)
    # equity 1.1, 0.55, 0.66, 1.32 -> max DD -50%, recovered on day 4
    assert abs(m.max_drawdown(r) - (-0.5)) < 1e-12
    assert m.max_drawdown_duration_days(r) == (IDX[3] - IDX[0]).days
    assert abs(m.calmar_ratio(r) - m.cagr(r) / 0.5) < 1e-12


def test_sharpe_sortino_var() -> None:
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.001, 0.01, 5000))
    assert abs(m.sharpe_ratio(r) - r.mean() / r.std() * np.sqrt(252)) < 1e-12
    assert m.sortino_ratio(r) > m.sharpe_ratio(r)  # symmetric noise: downside dev < total dev
    assert m.historical_cvar(r, 0.95) <= m.historical_var(r, 0.95) < 0
    assert math.isnan(m.sharpe_ratio(pd.Series([0.01] * 10)))  # zero variance


def test_monthly_yearly_and_bundle() -> None:
    idx = pd.bdate_range("2021-01-01", "2022-12-31")
    r = pd.Series(0.0005, index=idx)
    y = m.yearly_returns(r)
    assert len(y) == 2 and all(v > 0 for v in y)
    assert m.best_month(r) >= m.worst_month(r)
    bundle = m.compute_metrics(r)
    assert bundle.win_rate == 1.0 and bundle.max_drawdown == 0.0


if __name__ == "__main__":
    test_cagr_and_total_growth()
    test_drawdown_and_duration()
    test_sharpe_sortino_var()
    test_monthly_yearly_and_bundle()
    print("All metrics tests passed.")
