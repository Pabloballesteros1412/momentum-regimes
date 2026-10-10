"""Replay a finished walk-forward's trading folds to recover its holdings.

run_walkforward returns equity curves only. To ask *what* a walk-forward
held (sector attribution, crash anatomy), this re-runs each trading window
with the parameters that fold actually chose -- read from a persisted folds
CSV -- using exactly run_walkforward's own trading-window recipe: frames
sliced from trade_start - warmup_days, the strategy told not to act before
trade_start, capital chained from the previous fold's last out-of-sample
equity. The backtest is deterministic, so the replayed out-of-sample curve
must equal the stored one exactly; callers should check that (see
`max_equity_gap`) before trusting the holdings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from ..data.handler import DataHandler
from ..engine.backtest import Backtest
from ..engine.broker import SimulatedBroker
from ..portfolio.portfolio import Portfolio
from .walkforward import _slice_frames


@dataclass
class ReplayResult:
    equity_curve: pd.DataFrame  # concatenated out-of-sample curve, like WalkForwardResult's
    rebalances: list[pd.Timestamp] = field(default_factory=list)
    # Position quantities after each rebalance's orders have settled, keyed by rebalance date.
    holdings: dict[pd.Timestamp, dict[str, int]] = field(default_factory=dict)
    # Market value per symbol on the settlement bar, keyed by rebalance date.
    holdings_value: dict[pd.Timestamp, dict[str, float]] = field(default_factory=dict)
    # Names the strategy *selected* (LONG signals) at each rebalance. Under
    # engine v1 some selected names are never bought (cash starvation), so
    # this can differ from `holdings`.
    selections: dict[pd.Timestamp, set[str]] = field(default_factory=dict)
    # Daily end-of-day position quantities (rows: out-of-sample dates,
    # columns: symbols), positions reset at each fold like run_walkforward.
    positions: pd.DataFrame = field(default_factory=pd.DataFrame)

    def max_equity_gap(self, stored: pd.Series) -> float:
        """Largest relative difference between the replayed and a stored equity curve."""
        a = pd.DataFrame({"r": self.equity_curve["equity"], "s": stored}).dropna()
        return float(((a["r"] - a["s"]).abs() / a["s"].abs()).max())


def _recording(strategy_factory: Callable, log: list) -> Callable:
    """Wrap a strategy factory so every rebalance day the strategy acts on is logged."""

    def factory(data, **kwargs):
        strategy = strategy_factory(data, **kwargs)
        original = strategy.on_market

        def on_market(event):
            signals = original(event)
            if signals:
                log.append((pd.Timestamp(event.timestamp),
                            {x.symbol for x in signals if x.direction.name == "LONG"}))
            return signals

        strategy.on_market = on_market
        return strategy

    return factory


def replay_walkforward(
    frames: dict[str, pd.DataFrame],
    folds: pd.DataFrame,
    strategy_factory: Callable,
    sizer_factory: Callable,
    warmup_days: int,
    initial_capital: float = 100_000.0,
    shared_kwargs: dict | None = None,
    param_columns: tuple[str, ...] = ("lookback", "skip", "top_decile", "rebalance_freq"),
) -> ReplayResult:
    """Re-run every trading fold of a persisted walk-forward.

    `folds` needs trade_start, trade_end and the parameter columns (the
    *_folds.csv files written by run_cash_v2.py / run_regimes_reversal.py).
    A missing rebalance_freq column defaults to "monthly".
    """
    shared_kwargs = shared_kwargs or {}
    capital = initial_capital
    curves, rebalances = [], []
    holdings: dict[pd.Timestamp, dict[str, int]] = {}
    values: dict[pd.Timestamp, dict[str, float]] = {}
    selections: dict[pd.Timestamp, set[str]] = {}
    position_frames: list[pd.DataFrame] = []

    for _, f in folds.iterrows():
        trade_start, trade_end = pd.Timestamp(f["trade_start"]), pd.Timestamp(f["trade_end"])
        params = {c: f[c] for c in param_columns if c in f.index}
        params.setdefault("rebalance_freq", "monthly")
        for k in ("lookback", "skip"):
            if k in params:
                params[k] = int(params[k])
        params["top_decile"] = float(params["top_decile"])

        trade_frames = _slice_frames(frames, trade_start - pd.Timedelta(days=warmup_days), trade_end)
        log: list[tuple[pd.Timestamp, set[str]]] = []
        data = DataHandler(trade_frames)
        portfolio = Portfolio(data, initial_capital=capital)
        strategy = _recording(strategy_factory, log)(data, **params, active_from=trade_start, **shared_kwargs)
        sizer = sizer_factory(data, portfolio)
        Backtest(data, strategy, sizer, SimulatedBroker(data), portfolio).run()

        curve = portfolio.equity_curve()
        oos = curve.loc[curve.index >= trade_start].copy()
        curves.append(oos)
        capital = float(oos["equity"].iloc[-1])

        # Positions after each rebalance: fills settle on the next bar.
        fills = pd.DataFrame([{"ts": pd.Timestamp(x.timestamp), "symbol": x.symbol, "qty": x.quantity}
                              for x in portfolio.fills])
        timeline = data.timeline
        position_frames.append(daily_positions(portfolio.fills, curve.index).loc[oos.index])
        for d, selected in log:
            selections[d] = selected
            i = timeline.get_loc(d)
            settle = timeline[min(i + 1, len(timeline) - 1)]
            pos = fills[fills["ts"] <= settle].groupby("symbol")["qty"].sum() if len(fills) else pd.Series(dtype=int)
            pos = pos[pos != 0]
            holdings[d] = {s: int(q) for s, q in pos.items()}
            values[d] = {s: float(q) * float(trade_frames[s]["close"].asof(settle)) for s, q in pos.items()}
            rebalances.append(d)

    combined = pd.concat(curves).sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]
    combined["returns"] = combined["equity"].pct_change().fillna(0.0)
    positions = pd.concat(position_frames).fillna(0.0)
    positions = positions[~positions.index.duplicated(keep="first")]
    return ReplayResult(equity_curve=combined, rebalances=rebalances, holdings=holdings, holdings_value=values,
                        selections=selections, positions=positions)


def daily_positions(fills: list, index: pd.DatetimeIndex) -> pd.DataFrame:
    """End-of-day position quantity per symbol from a Portfolio's fills
    (a fill is stamped with the bar it executed on)."""
    if not fills:
        return pd.DataFrame(index=index)
    df = pd.DataFrame([{"ts": pd.Timestamp(x.timestamp), "symbol": x.symbol, "qty": x.quantity} for x in fills])
    q = df.pivot_table(index="ts", columns="symbol", values="qty", aggfunc="sum").fillna(0.0).cumsum()
    return q.reindex(index.union(q.index)).ffill().fillna(0.0).reindex(index)
