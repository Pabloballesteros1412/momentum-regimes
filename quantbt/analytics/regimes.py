"""Market regime classification using SPY as the reference index.

Two independent legs, combined into four regimes:

  - Trend: "bullish" if SPY's close is above its trailing 200-session SMA,
    "bearish" otherwise.
  - Volatility: "high" if SPY's 21-day realized volatility exceeds its own
    75th percentile computed *expanding* -- using only data up to and
    including that day -- "low" otherwise.

Both legs are strictly point-in-time. The trend SMA is a trailing rolling
window (never sees ahead), and the volatility threshold is an expanding
quantile (pandas .expanding().quantile(), which by construction only ever
aggregates rows at or before the one being computed) -- never a quantile
taken once over the full sample and applied retroactively. That is the
one thing this module must never do, since it would let a later regime
(known only in hindsight) leak into how an earlier day is labeled.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252

REGIME_LABELS: list[str] = ["bullish_low", "bullish_high", "bearish_low", "bearish_high"]


@dataclass(frozen=True)
class RegimeConfig:
    trend_window: int = 200
    vol_window: int = 21
    vol_percentile: float = 0.75
    # Minimum number of expanding-window observations before a volatility
    # percentile is trusted enough to assign a label.
    min_vol_history: int = 252


def classify_regimes(price: pd.Series, config: RegimeConfig = RegimeConfig()) -> pd.DataFrame:
    """Classify every day in `price` into a trend x volatility regime.

    `price` is a Series of daily closing levels (e.g. SPY), indexed by
    date. Returns a DataFrame aligned to the same index with the
    intermediate series (sma_200, realized_vol_21, the expanding vol
    threshold) alongside the trend/volatility/regime labels, so the
    classification is auditable rather than a black box.
    """
    price = price.sort_index()

    sma = price.rolling(config.trend_window, min_periods=config.trend_window).mean()
    trend = pd.Series(np.where(price > sma, "bullish", "bearish"), index=price.index, dtype=object)
    trend[sma.isna()] = None

    daily_returns = price.pct_change()
    realized_vol = daily_returns.rolling(config.vol_window, min_periods=config.vol_window).std() * np.sqrt(
        TRADING_DAYS_PER_YEAR
    )
    # Expanding, not global: the quantile at row i uses only rows [0, i].
    vol_threshold = realized_vol.expanding(min_periods=config.min_vol_history).quantile(config.vol_percentile)

    volatility = pd.Series(
        np.where(realized_vol > vol_threshold, "high", "low"), index=price.index, dtype=object
    )
    volatility[vol_threshold.isna() | realized_vol.isna()] = None

    has_both = trend.notna() & volatility.notna()
    regime = pd.Series(None, index=price.index, dtype=object)
    regime[has_both] = trend[has_both].astype(str) + "_" + volatility[has_both].astype(str)

    return pd.DataFrame(
        {
            "close": price,
            "sma_200": sma,
            "trend": trend,
            "realized_vol_21": realized_vol,
            "vol_threshold_75pct_expanding": vol_threshold,
            "volatility": volatility,
            "regime": regime,
        },
        index=price.index,
    )
