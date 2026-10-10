"""Point-in-time index membership.

A UniverseSchedule answers "was `symbol` an index member on `date`?" from
per-symbol membership intervals (e.g. data/sp500_membership_intervals.csv,
built by build_universe_us.py). Strategies opt in to it; nothing in the
default engine path reads it.
"""

from __future__ import annotations

from bisect import bisect_right
from pathlib import Path

import pandas as pd


class UniverseSchedule:
    def __init__(self, intervals: pd.DataFrame) -> None:
        """`intervals`: columns ticker, start, end (inclusive dates)."""
        self._starts: dict[str, list[pd.Timestamp]] = {}
        self._ends: dict[str, list[pd.Timestamp]] = {}
        intervals = intervals.assign(start=pd.to_datetime(intervals["start"]), end=pd.to_datetime(intervals["end"]))
        for ticker, g in intervals.sort_values("start").groupby("ticker"):
            self._starts[ticker] = list(pd.to_datetime(g["start"]))
            self._ends[ticker] = list(pd.to_datetime(g["end"]))

    @classmethod
    def from_csv(cls, path: str | Path) -> "UniverseSchedule":
        return cls(pd.read_csv(path, parse_dates=["start", "end"]))

    @property
    def tickers(self) -> list[str]:
        return sorted(self._starts)

    def is_member(self, symbol: str, date) -> bool:
        starts = self._starts.get(symbol)
        if not starts:
            return False
        ts = pd.Timestamp(date)
        i = bisect_right(starts, ts) - 1
        return i >= 0 and ts <= self._ends[symbol][i]

    def members(self, date, among=None) -> list[str]:
        pool = self._starts if among is None else among
        return [s for s in pool if self.is_member(s, date)]
