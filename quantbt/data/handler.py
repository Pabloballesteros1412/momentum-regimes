"""Data ingestion and controlled, point-in-time bar delivery.

The critical design rule: a strategy can only ever ask for data through
`get_latest_bars()`, which is capped at the current simulation timestamp.
The full price history exists in memory, but there is no API path that
exposes future rows.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


class DataHandler:
    """Holds OHLCV history for a universe and drip-feeds it chronologically."""

    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        if not frames:
            raise ValueError("DataHandler requires at least one symbol")

        self._frames = {sym: df.sort_index() for sym, df in frames.items()}
        self._validate()

        # Union of all trading days across the universe.
        index = pd.DatetimeIndex([])
        for df in self._frames.values():
            index = index.union(df.index)
        self.timeline: pd.DatetimeIndex = index

        self._cursor: int = -1

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def from_yfinance(
        cls,
        symbols: list[str],
        start: str,
        end: str,
        cache_dir: str | Path = "cache",
    ) -> "DataHandler":
        """Download adjusted OHLCV from Yahoo Finance, with on-disk caching.

        Adjusted prices matter: unadjusted series show fake overnight gaps on
        ex-dividend and split dates, which momentum strategies happily trade.
        """
        import yfinance as yf

        cache = Path(cache_dir)
        cache.mkdir(parents=True, exist_ok=True)

        frames: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            cache_file = cache / f"{symbol}_{start}_{end}.parquet"

            if cache_file.exists():
                frames[symbol] = pd.read_parquet(cache_file)
                continue

            raw = yf.download(
                symbol,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
            )
            if raw.empty:
                raise ValueError(f"No data returned for {symbol}")

            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            raw.columns = [str(c).lower() for c in raw.columns]
            raw = raw[["open", "high", "low", "close", "volume"]]
            raw.index.name = "timestamp"

            raw.to_parquet(cache_file)
            frames[symbol] = raw

        return cls(frames)

    def _validate(self) -> None:
        required = {"open", "high", "low", "close", "volume"}
        for symbol, df in self._frames.items():
            missing = required - set(df.columns)
            if missing:
                raise ValueError(f"{symbol} is missing columns: {sorted(missing)}")
            if not isinstance(df.index, pd.DatetimeIndex):
                raise TypeError(f"{symbol} index must be a DatetimeIndex")
            if df.index.has_duplicates:
                raise ValueError(f"{symbol} has duplicate timestamps")

    # ------------------------------------------------------------------
    # Simulation clock
    # ------------------------------------------------------------------
    @property
    def symbols(self) -> list[str]:
        """Every symbol the handler holds, in insertion order."""
        return list(self._frames)

    @property
    def frames(self) -> dict[str, pd.DataFrame]:
        """Full OHLCV history per symbol, unrestricted by the simulation clock.

        For orchestration code that needs to re-slice the whole dataset
        into other DataHandlers (e.g. walk-forward train/trade windows) --
        not for strategies, which must stay on get_latest_bars().
        """
        return dict(self._frames)

    @property
    def current_time(self) -> datetime:
        """Timestamp of the bar the simulation clock is on."""
        if self._cursor < 0:
            raise RuntimeError("Clock has not started; call advance() first")
        return self.timeline[self._cursor].to_pydatetime()

    def advance(self) -> bool:
        """Move the clock one bar forward. Returns False when history ends."""
        if self._cursor + 1 >= len(self.timeline):
            return False
        self._cursor += 1
        return True

    # ------------------------------------------------------------------
    # Point-in-time accessors
    # ------------------------------------------------------------------
    def get_latest_bars(self, symbol: str, n: int = 1) -> pd.DataFrame:
        """Return the last `n` bars up to and including the current timestamp."""
        df = self._frames[symbol]
        visible = df.loc[: self.timeline[self._cursor]]
        return visible.tail(n)

    def get_latest_close(self, symbol: str) -> float | None:
        """Latest visible close for `symbol`, or None if it has no bar yet."""
        bars = self.get_latest_bars(symbol, 1)
        if bars.empty:
            return None
        return float(bars["close"].iloc[-1])

    def get_next_open(self, symbol: str) -> float | None:
        """Execution reference price for the broker only.

        Deliberately NOT exposed to strategies: this is next-bar information.
        Orders generated on bar t are filled at the open of bar t+1, which is
        the earliest price a real trader could realistically obtain.
        """
        if self._cursor + 1 >= len(self.timeline):
            return None
        next_ts = self.timeline[self._cursor + 1]
        df = self._frames[symbol]
        if next_ts not in df.index:
            return None
        return float(df.at[next_ts, "open"])

    def has_data(self, symbol: str) -> bool:
        """Whether `symbol` has at least one bar visible at the current time."""
        return not self.get_latest_bars(symbol, 1).empty
