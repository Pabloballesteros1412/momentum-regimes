"""Stress testing: isolate specific historical windows and score each
equity curve using only the data inside them.

Return, max drawdown, and worst day are all computed strictly within the
window: it is renormalized to its own first bar, so nothing outside it can
leak into these three numbers. Recovery time is the one exception by
necessity -- "how long to recover" is inherently forward-looking. It
measures from the peak that precedes the window's worst drawdown (found
using only window data -- for a window that opens before its true local
high, such as "COVID crash" opening Feb 1 while the S&P 500 kept rising
until Feb 19, that peak lands partway through the window, not on its first
bar) and is then free to keep searching past the window's end for the day
that peak is regained.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class StressWindow:
    name: str
    start: str  # "YYYY-MM-DD"
    end: str  # inclusive


STRESS_WINDOWS: list[StressWindow] = [
    StressWindow("COVID crash", "2020-02-01", "2020-03-31"),
    StressWindow("COVID recovery", "2020-04-01", "2020-12-31"),
    StressWindow("2022 bear market", "2022-01-01", "2022-10-31"),
    StressWindow("2023 rally", "2023-01-01", "2023-12-31"),
]


@dataclass
class StressResult:
    window: str
    start: pd.Timestamp
    end: pd.Timestamp
    has_data: bool
    total_return: float
    max_drawdown: float
    worst_day: float
    days_to_recover: int | None  # None: not (yet) recovered in available data


def _slice(curve: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    return curve.loc[(curve.index >= start) & (curve.index <= end)]


def evaluate_window(curve: pd.Series, window: StressWindow) -> StressResult:
    """Score one equity curve against one stress window."""
    start = pd.Timestamp(window.start)
    end = pd.Timestamp(window.end)
    windowed = _slice(curve, start, end)

    if windowed.empty:
        return StressResult(window.name, start, end, False, float("nan"), float("nan"), float("nan"), None)

    total_return = float(windowed.iloc[-1] / windowed.iloc[0] - 1.0)

    daily_returns = windowed.pct_change().dropna()
    worst_day = float(daily_returns.min()) if not daily_returns.empty else float("nan")

    running_max = windowed.cummax()
    drawdown = windowed / running_max - 1.0
    max_drawdown = float(drawdown.min())

    # The peak preceding the window's worst trough -- may be the window's
    # own opening bar, or a later one if the window opens before the true
    # local high (see module docstring).
    trough_idx = drawdown.idxmin()
    peak_value = float(running_max.loc[trough_idx])
    pre_trough = windowed.loc[:trough_idx]
    peak_idx = pre_trough.where(pre_trough >= peak_value).last_valid_index()

    after_peak = curve[curve.index > peak_idx]
    recovered = after_peak[after_peak >= peak_value]
    days_to_recover = int((recovered.index[0] - peak_idx).days) if not recovered.empty else None

    return StressResult(window.name, start, end, True, total_return, max_drawdown, worst_day, days_to_recover)


def run_stress_test(
    equity_curves: dict[str, pd.Series],
    windows: list[StressWindow] | None = None,
) -> pd.DataFrame:
    """Score every (window, strategy) pair. Returns one row per pair."""
    windows = STRESS_WINDOWS if windows is None else windows
    rows = []
    for window in windows:
        for label, curve in equity_curves.items():
            result = evaluate_window(curve, window)
            rows.append(
                {
                    "window": result.window,
                    "start": result.start,
                    "end": result.end,
                    "strategy": label,
                    "has_data": result.has_data,
                    "return": result.total_return,
                    "max_drawdown": result.max_drawdown,
                    "worst_day": result.worst_day,
                    "days_to_recover": result.days_to_recover,
                }
            )
    return pd.DataFrame(rows)
