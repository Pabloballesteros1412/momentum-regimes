"""Walk-forward analysis engine.

Rolls a training window of N years and a trading window of M years forward
through the data, M years at a time. In each training window it grid-
searches a parameter space and keeps the combination with the best Sharpe
ratio -- not total return, since return alone rewards taking risk, not
managing it. Those parameters are then run, completely unchanged, on the
trading window that immediately follows. The training window is never
allowed to see the trading window: every fold asserts that its training
data ends at or before its trading data begins, both from the nominal
fold boundaries and from the actual dates present in the sliced data.

The out-of-sample equity curve from every fold is concatenated into one
continuous series, each fold picking up where the previous one's capital
left off.

Trading windows are given a slice of history that starts `warmup_days`
before their nominal start, purely so lookback-based indicators (e.g. a
252-day momentum window) are already valid on day one -- that data is
still strictly historical as of the trading window and was never used to
select parameters. `trade_extra_kwargs`, if given, lets the caller tell
the strategy not to actually act on that warm-up stretch (see
CrossSectionalMomentum's `active_from`); without it, a strategy free to
trade during warm-up would carry P&L across the fold boundary that has no
clean place in the concatenated curve.

The training grid search is the expensive part -- every combination in
param_grid is an independent backtest against the *same* train_frames, so
it is farmed out to a process pool (`n_jobs`, default os.cpu_count() - 1).
`strategy_shared_kwargs` is for state that's expensive to build once but
wasteful to rebuild per combination (e.g. CrossSectionalMomentum's
SignalCache) -- it's merged into every strategy construction call, train
and trade alike, without becoming part of the tuned grid or the reported
Fold.params. This module has no idea what any of that state means; it
just distributes it to worker processes once per fold via the pool
initializer, rather than pickling it onto every one of param_grid's tasks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from multiprocessing import Pool
from typing import Callable

import pandas as pd

from ..data.handler import DataHandler
from ..engine.backtest import Backtest
from ..engine.broker import SimulatedBroker
from ..portfolio.portfolio import Portfolio
from ..risk.sizing import PositionSizer
from ..strategies.base import Strategy

StrategyFactory = Callable[..., Strategy]
SizerFactory = Callable[[DataHandler, Portfolio], PositionSizer]


@dataclass
class Fold:
    """One training/trading iteration of the walk-forward loop."""

    train_start: pd.Timestamp
    train_end: pd.Timestamp
    trade_start: pd.Timestamp
    trade_end: pd.Timestamp
    params: dict
    train_sharpe: float
    equity_curve: pd.DataFrame  # out-of-sample only: index >= trade_start


@dataclass
class WalkForwardResult:
    folds: list[Fold]
    equity_curve: pd.DataFrame  # concatenated out-of-sample curve, all folds
    initial_capital: float


def _slice_frames(
    frames: dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp
) -> dict[str, pd.DataFrame]:
    """Half-open [start, end) slice of every symbol's history."""
    sliced = {}
    for symbol, df in frames.items():
        window = df.loc[(df.index >= start) & (df.index < end)]
        if not window.empty:
            sliced[symbol] = window
    return sliced


def _generate_folds(
    dataset_start: pd.Timestamp,
    dataset_end: pd.Timestamp,
    train_years: int,
    trade_years: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    folds = []
    train_start = dataset_start
    while True:
        train_end = train_start + pd.DateOffset(years=train_years)
        trade_start = train_end
        trade_end = trade_start + pd.DateOffset(years=trade_years)
        if trade_start >= dataset_end:
            break
        folds.append((train_start, train_end, trade_start, trade_end))
        train_start = train_start + pd.DateOffset(years=trade_years)
    return folds


def _sharpe_ratio(curve: pd.DataFrame) -> float:
    """Annualized Sharpe of a Portfolio.equity_curve(), zero risk-free rate."""
    returns = curve["returns"]
    std = returns.std()
    if not std or pd.isna(std):
        return float("-inf")
    return float(returns.mean() / std * (252 ** 0.5))


def _run_backtest(
    frames: dict[str, pd.DataFrame],
    strategy_factory: StrategyFactory,
    strategy_kwargs: dict,
    sizer_factory: SizerFactory,
    initial_capital: float,
) -> Portfolio:
    data = DataHandler(frames)
    portfolio = Portfolio(data, initial_capital=initial_capital)
    strategy = strategy_factory(data, **strategy_kwargs)
    sizer = sizer_factory(data, portfolio)
    broker = SimulatedBroker(data)
    backtest = Backtest(data, strategy, sizer, broker, portfolio, verbose=False)
    backtest.run()
    return portfolio


# Populated by _pool_init in each worker process; a plain module global is
# the standard way to hand a Pool's workers read-only state without
# re-pickling it onto every task (see module docstring).
_POOL_STATE: dict = {}


def _pool_init(
    train_frames: dict[str, pd.DataFrame],
    strategy_factory: StrategyFactory,
    sizer_factory: SizerFactory,
    initial_capital: float,
    shared_kwargs: dict,
) -> None:
    global _POOL_STATE
    _POOL_STATE = {
        "train_frames": train_frames,
        "strategy_factory": strategy_factory,
        "sizer_factory": sizer_factory,
        "initial_capital": initial_capital,
        "shared_kwargs": shared_kwargs,
    }


def _pool_evaluate(params: dict) -> tuple[dict, float]:
    state = _POOL_STATE
    strategy_kwargs = {**params, **state["shared_kwargs"]}
    portfolio = _run_backtest(
        state["train_frames"], state["strategy_factory"], strategy_kwargs,
        state["sizer_factory"], state["initial_capital"],
    )
    return params, _sharpe_ratio(portfolio.equity_curve())


def _select_best_params(
    train_frames: dict[str, pd.DataFrame],
    param_grid: list[dict],
    strategy_factory: StrategyFactory,
    sizer_factory: SizerFactory,
    initial_capital: float,
    shared_kwargs: dict | None = None,
    n_jobs: int = 1,
) -> tuple[dict, float]:
    """Grid search restricted entirely to train_frames. Best Sharpe wins."""
    shared_kwargs = shared_kwargs or {}

    if n_jobs <= 1:
        results = []
        for params in param_grid:
            strategy_kwargs = {**params, **shared_kwargs}
            portfolio = _run_backtest(train_frames, strategy_factory, strategy_kwargs, sizer_factory, initial_capital)
            results.append((params, _sharpe_ratio(portfolio.equity_curve())))
    else:
        with Pool(
            processes=n_jobs,
            initializer=_pool_init,
            initargs=(train_frames, strategy_factory, sizer_factory, initial_capital, shared_kwargs),
        ) as pool:
            results = pool.map(_pool_evaluate, param_grid)

    best_params, best_sharpe = max(results, key=lambda r: r[1])
    return best_params, best_sharpe


def run_walkforward(
    frames: dict[str, pd.DataFrame],
    param_grid: list[dict],
    strategy_factory: StrategyFactory,
    sizer_factory: SizerFactory,
    train_years: int = 4,
    trade_years: int = 1,
    initial_capital: float = 100_000.0,
    warmup_days: int = 400,
    trade_extra_kwargs: Callable[[pd.Timestamp], dict] | None = None,
    strategy_shared_kwargs: dict | None = None,
    n_jobs: int | None = None,
    progress: Callable[[str], None] | None = None,
    on_fold_complete: Callable[[int, Fold], None] | None = None,
) -> WalkForwardResult:
    """
    strategy_shared_kwargs: merged into every strategy construction call
        (training grid search AND the final trading-window run), for state
        that's expensive to build once but wasteful to rebuild per grid
        combination -- e.g. CrossSectionalMomentum's SignalCache. Not part
        of the tuned grid: never appears in the best-params this function
        selects or reports.
    n_jobs: worker processes for the per-fold grid search. None (default)
        uses os.cpu_count() - 1; 1 runs sequentially in-process.
    progress: optional callback(message) for coarse-grained status text
        (fold N/M starting, training done, trading done). No timestamp is
        added here -- the caller's callback controls formatting.
    on_fold_complete: optional callback(fold_index, Fold), called right
        after each fold's Fold record is built, before moving to the next
        one -- the hook for persisting partial results incrementally.
    """
    if n_jobs is None:
        n_jobs = max(1, (os.cpu_count() or 2) - 1)
    shared_kwargs = strategy_shared_kwargs or {}

    def _report(message: str) -> None:
        if progress is not None:
            progress(message)

    dataset_start = min(df.index.min() for df in frames.values())
    dataset_end = max(df.index.max() for df in frames.values())

    fold_bounds = _generate_folds(dataset_start, dataset_end, train_years, trade_years)
    if not fold_bounds:
        raise ValueError(
            f"Date range {dataset_start.date()} - {dataset_end.date()} is too short "
            f"for a {train_years}y train / {trade_years}y trade window"
        )

    folds: list[Fold] = []
    oos_curves: list[pd.DataFrame] = []
    capital = initial_capital
    n_folds = len(fold_bounds)

    for fold_index, (train_start, train_end, trade_start, trade_end) in enumerate(fold_bounds, start=1):
        # The one rule this whole module exists to enforce: parameter
        # selection must never see the window it will be graded on.
        assert train_start < train_end, "Training window must have positive length"
        assert trade_start < trade_end, "Trading window must have positive length"
        assert train_end <= trade_start, (
            "Training window must end at or before the trading window starts: "
            f"train_end={train_end} trade_start={trade_start}"
        )

        _report(
            f"fold {fold_index}/{n_folds}: training on [{train_start.date()}, {train_end.date()}) "
            f"-- {len(param_grid)} combinations, n_jobs={n_jobs}"
        )

        train_frames = _slice_frames(frames, train_start, train_end)
        if train_frames:
            train_max_date = max(df.index.max() for df in train_frames.values())
            assert train_max_date < trade_start, (
                "Training data reaches into the trading window: latest training "
                f"bar {train_max_date} is not before trade_start {trade_start}"
            )

        best_params, best_sharpe = _select_best_params(
            train_frames, param_grid, strategy_factory, sizer_factory, initial_capital,
            shared_kwargs=shared_kwargs, n_jobs=n_jobs,
        )
        _report(f"fold {fold_index}/{n_folds}: training done -- best sharpe={best_sharpe:.2f} params={best_params}")

        # Warm-up history precedes trade_start but is never used for
        # selection above; trade_extra_kwargs is what stops the strategy
        # from actually trading on it (see module docstring).
        warmup_start = trade_start - pd.Timedelta(days=warmup_days)
        trade_frames = _slice_frames(frames, warmup_start, trade_end)
        extra_kwargs = trade_extra_kwargs(trade_start) if trade_extra_kwargs else {}

        portfolio = _run_backtest(
            trade_frames, strategy_factory, {**best_params, **extra_kwargs, **shared_kwargs}, sizer_factory, capital
        )
        full_curve = portfolio.equity_curve()
        oos_curve = full_curve.loc[full_curve.index >= trade_start].copy()
        if oos_curve.empty:
            raise RuntimeError(f"Fold trade_start={trade_start} produced no out-of-sample bars")

        fold = Fold(
            train_start=train_start,
            train_end=train_end,
            trade_start=trade_start,
            trade_end=trade_end,
            params=best_params,
            train_sharpe=best_sharpe,
            equity_curve=oos_curve,
        )
        folds.append(fold)
        oos_curves.append(oos_curve)
        capital = float(oos_curve["equity"].iloc[-1])

        _report(
            f"fold {fold_index}/{n_folds}: trading window [{trade_start.date()}, {trade_end.date()}) done "
            f"-- ending equity={capital:,.2f}"
        )
        if on_fold_complete is not None:
            on_fold_complete(fold_index, fold)

    combined = pd.concat(oos_curves).sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]
    combined["returns"] = combined["equity"].pct_change().fillna(0.0)
    combined["cumulative"] = (1.0 + combined["returns"]).cumprod()
    combined["drawdown"] = combined["cumulative"] / combined["cumulative"].cummax() - 1.0

    return WalkForwardResult(folds=folds, equity_curve=combined, initial_capital=initial_capital)
