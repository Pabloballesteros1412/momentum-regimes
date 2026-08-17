"""Point-in-time correctness test for quantbt.analytics.regimes.

Plain assert-based, run directly: `python test_regimes.py` -- matches the
convention already used by test_pipeline.py, no pytest dependency.

The property under test: nothing about day t's regime classification may
change once more data (t+1, or many more days) becomes available. Both the
trend leg (a trailing rolling SMA) and the volatility leg (an expanding
percentile) are supposed to guarantee this by construction; this test
verifies that guarantee actually holds for the code as written, not just
in theory.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbt.analytics.regimes import RegimeConfig, classify_regimes

CHECK_COLUMNS = [
    "sma_200",
    "trend",
    "realized_vol_21",
    "vol_threshold_75pct_expanding",
    "volatility",
    "regime",
]


def synthetic_price(seed: int, n: int) -> pd.Series:
    """A price series with regime-switching volatility, so the vol leg has
    genuine high- and low-vol stretches to classify, not just noise."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2005-01-03", periods=n)
    vol = np.where((np.arange(n) // 300) % 2 == 0, 0.008, 0.022)
    daily_returns = rng.normal(0.0003, 1.0, n) * vol
    close = 100.0 * np.exp(np.cumsum(daily_returns))
    return pd.Series(close, index=dates, name="close")


def _assert_row_unchanged(row_full: pd.Series, row_partial: pd.Series, cutoff, extra_days: int) -> None:
    for col in CHECK_COLUMNS:
        a, b = row_full[col], row_partial[col]
        if isinstance(a, float) and isinstance(b, float) and np.isnan(a) and np.isnan(b):
            continue
        assert a == b, (
            f"Regime classification at {cutoff.date()} changed after appending "
            f"{extra_days} more day(s) of data: column '{col}' was {b!r}, became {a!r}"
        )


def test_point_in_time(seed: int = 0) -> None:
    n = 252 * 6
    price = synthetic_price(seed, n)
    full = classify_regimes(price)

    warmup = max(RegimeConfig().trend_window, RegimeConfig().min_vol_history)
    checkpoints = range(warmup + 10, n - 100, 47)  # sampled throughout, not just once

    checked = 0
    for i in checkpoints:
        cutoff = price.index[i]

        same_day = classify_regimes(price.iloc[: i + 1])
        _assert_row_unchanged(full.loc[cutoff], same_day.loc[cutoff], cutoff, extra_days=0)

        plus_one = classify_regimes(price.iloc[: i + 2])
        _assert_row_unchanged(full.loc[cutoff], plus_one.loc[cutoff], cutoff, extra_days=1)

        plus_many = classify_regimes(price.iloc[: i + 100])
        _assert_row_unchanged(full.loc[cutoff], plus_many.loc[cutoff], cutoff, extra_days=99)

        checked += 1

    assert checked > 20, "sanity check on the test itself: too few checkpoints were exercised"
    print(f"Point-in-time check passed at {checked} checkpoints (t, t+1, and t+99 all agree with the full run).")


def test_labels_are_sane() -> None:
    """Cheap sanity check that the labels mean what they claim, independent
    of the point-in-time property above."""
    price = synthetic_price(seed=1, n=252 * 6)
    result = classify_regimes(price)
    labeled = result.dropna(subset=["trend", "volatility"])

    bullish = labeled[labeled["trend"] == "bullish"]
    bearish = labeled[labeled["trend"] == "bearish"]
    assert (bullish["close"] > bullish["sma_200"]).all()
    assert (bearish["close"] <= bearish["sma_200"]).all()

    high_vol = labeled[labeled["volatility"] == "high"]
    low_vol = labeled[labeled["volatility"] == "low"]
    assert (high_vol["realized_vol_21"] > high_vol["vol_threshold_75pct_expanding"]).all()
    assert (low_vol["realized_vol_21"] <= low_vol["vol_threshold_75pct_expanding"]).all()

    assert set(labeled["trend"].unique()) == {"bullish", "bearish"}
    assert set(labeled["volatility"].unique()) == {"high", "low"}
    print("Label sanity check passed (trend/volatility match their own thresholds).")


if __name__ == "__main__":
    test_labels_are_sane()
    test_point_in_time()
    print("\nAll regime tests passed.")
