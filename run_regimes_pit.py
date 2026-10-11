"""US survivorship check: engine-v2 momentum on a point-in-time S&P 500 universe
(PLAN.md item 1, US only). Writes only under results/pit_us/.

Inputs: data/sp500_membership_intervals.csv and the Yahoo prices in
cache/pit/ (both from build_universe_us.py). Names Yahoo no longer has are
simply absent: they can't be ranked or held, so the result is still biased
upward, only less than the fixed 37-name list. build_universe_us.py's
coverage report says by how much.

Runs (same 2005-2024 period, 4y/1y folds, warm-up and 12-combination grid as
the regime study; engine v2):

  pit_momentum      PointInTimeMomentum, walk-forward, delisted names
                    liquidated at their last close
  pit_benchmark     equal weight across current members, monthly
                    (buy & hold can't be used: it would hold every name that
                    ever joined and never sell)
  pit_liquid40      breadth control: PIT, but only the 40 most liquid current
                    members (63-day dollar volume) are ranked
  (a -30% delisting-return sensitivity is implemented in the sizers but
   not run: no series in the free data ends early -- see DELISTING)

Compared with the fixed 37-name universe from results/v2 (momentum v2 vs
buy & hold v2) on the same out-of-sample days.

    python run_regimes_pit.py [runs|analyze]
"""

from __future__ import annotations

import sys
from datetime import datetime
from functools import partial
from pathlib import Path

import pandas as pd

from quantbt.analytics import metrics
from quantbt.analytics.significance import bootstrap_regime_differences
from quantbt.data.handler import DataHandler
from quantbt.data.universe import UniverseSchedule
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.strategies.momentum import SignalCache
from quantbt.strategies.pit import (PITEqualWeightSizer, PITVolatilityTargetSizer, PointInTimeEqualWeight,
                                    PointInTimeLiquidMomentum, PointInTimeMomentum)
from quantbt.validation.walkforward import run_walkforward
import run_regimes
from run_walkforward import TRADE_YEARS, TRAIN_YEARS

OUT = Path("results/pit_us")
CURVES = OUT / "curves"
CACHE = Path("cache/pit")
INTERVALS = Path("data/sp500_membership_intervals.csv")
EXCLUDED = Path("data/sp500_excluded_tickers.txt")
V2_CURVES = Path("results/v2/curves")
REGIME_CSV = Path("results/v2/spy_regime_rerun.csv")
WARMUP_DAYS = int(max(run_regimes.REDUCED_LOOKBACKS) * 7 / 5) + 30
# A -30% Shumway (1997) delisting return was planned as a sensitivity, but
# it can never trigger: every one of the 622 Yahoo series runs to the end of
# 2024 (Yahoo keeps only still-listed symbols), so no held name's data ends
# early. The run would equal the base exactly, so it is not run.
DELISTING = {"base": 0.0}
N_ITERATIONS, BLOCK_SIZE, CONFIDENCE = 5000, 20, 0.95


def _log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _frames() -> dict[str, pd.DataFrame]:
    excluded = set(EXCLUDED.read_text().split())  # reused tickers, see build_universe_us.py
    frames = {}
    for f in sorted(CACHE.glob("*.parquet")):
        if f.stem in excluded:
            continue
        df = pd.read_parquet(f)
        df = df.loc[run_regimes.START:run_regimes.END]
        if len(df) > 1 and not df.index.has_duplicates:
            frames[f.stem] = df
    return frames


def _save(name: str, curve: pd.DataFrame, fold_starts=()) -> None:
    df = curve[["cash", "holdings", "equity", "returns"]].copy()
    df.index.name = "date"
    df["fold_start"] = df.index.isin(pd.DatetimeIndex(list(fold_starts)))
    df.to_csv(CURVES / f"{name}.csv", float_format="%.17g")


def _load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, index_col="date", parse_dates=["date"], float_precision="round_trip")


def stage_runs() -> None:
    CURVES.mkdir(parents=True, exist_ok=True)
    schedule = UniverseSchedule.from_csv(INTERVALS)
    frames = _frames()
    _log(f"{len(frames)} names with prices; {len(schedule.tickers)} ever members")
    cache = SignalCache.build(frames)
    for label, dr in DELISTING.items():
        name = f"pit_benchmark_{label}"
        if not (CURVES / f"{name}.csv").exists():
            _log(f"benchmark ({label})")
            data = DataHandler(frames)
            pf = Portfolio(data, initial_capital=100_000.0)
            strategy = PointInTimeEqualWeight(data, schedule)
            sizer = PITEqualWeightSizer(data, pf, engine_version="v2", delisting_return=dr)
            sizer.strategy = strategy
            Backtest(data, strategy, sizer, SimulatedBroker(data), pf).run()
            _save(name, pf.equity_curve())
            pd.DataFrame(sizer.liquidations, columns=["date", "symbol"]).to_csv(
                CURVES / f"{name}_liquidations.csv", index=False)

        name = f"pit_momentum_{label}"
        if not (CURVES / f"{name}.csv").exists():
            wf = run_walkforward(
                frames=frames, param_grid=run_regimes._param_grid(), strategy_factory=PointInTimeMomentum,
                sizer_factory=partial(PITVolatilityTargetSizer, engine_version="v2", delisting_return=dr),
                train_years=TRAIN_YEARS, trade_years=TRADE_YEARS, initial_capital=100_000.0,
                warmup_days=WARMUP_DAYS, trade_extra_kwargs=lambda t: {"active_from": t},
                strategy_shared_kwargs={"signal_cache": cache, "schedule": schedule},
                n_jobs=run_regimes.N_JOBS, progress=lambda m: _log(f"[PIT momentum {label}] {m}"),
            )
            pd.DataFrame([{"fold_index": i, "trade_start": f.trade_start.date(), "trade_end": f.trade_end.date(),
                           **f.params, "train_sharpe": f.train_sharpe} for i, f in enumerate(wf.folds, 1)]
                         ).to_csv(CURVES / f"{name}_folds.csv", index=False)
            _save(name, wf.equity_curve, [f.equity_curve.index[0] for f in wf.folds])

    # Breadth control: point-in-time, but only the 40 most liquid current
    # members are ranked -- about as narrow as the fixed 37-name list.
    name = "pit_liquid40_momentum_base"
    if not (CURVES / f"{name}.csv").exists():
        wf = run_walkforward(
            frames=frames, param_grid=run_regimes._param_grid(),
            strategy_factory=partial(PointInTimeLiquidMomentum, top_n_liquid=40),
            sizer_factory=partial(PITVolatilityTargetSizer, engine_version="v2", delisting_return=0.0),
            train_years=TRAIN_YEARS, trade_years=TRADE_YEARS, initial_capital=100_000.0,
            warmup_days=WARMUP_DAYS, trade_extra_kwargs=lambda t: {"active_from": t},
            strategy_shared_kwargs={"signal_cache": cache, "schedule": schedule},
            n_jobs=run_regimes.N_JOBS, progress=lambda m: _log(f"[PIT liquid-40 momentum] {m}"),
        )
        pd.DataFrame([{"fold_index": i, "trade_start": f.trade_start.date(), "trade_end": f.trade_end.date(),
                       **f.params, "train_sharpe": f.train_sharpe} for i, f in enumerate(wf.folds, 1)]
                     ).to_csv(CURVES / f"{name}_folds.csv", index=False)
        _save(name, wf.equity_curve, [f.equity_curve.index[0] for f in wf.folds])


def _row(label: str, mom: pd.Series, bench: pd.Series, regime: pd.Series, curve: pd.DataFrame) -> dict:
    a = pd.DataFrame({"m": mom, "b": bench, "regime": regime}).dropna()
    trend = a["regime"].str.split("_").str[0]
    res = bootstrap_regime_differences(a["m"] - a["b"], trend, ["bullish", "bearish"], confidence=CONFIDENCE,
                                       block_size=BLOCK_SIZE, n_iterations=N_ITERATIONS, seed=0).iloc[0]
    inv = (curve["holdings"] / curve["equity"]).loc[a.index]
    out = {"universe": label, "start": a.index.min().date(), "end": a.index.max().date(), "days": len(a),
           "mean_invested_momentum": float(inv.mean())}
    for key, r in (("momentum", a["m"]), ("benchmark", a["b"])):
        out.update({f"{key}_total_return": float((1 + r).prod() - 1), f"{key}_cagr": metrics.cagr(r),
                    f"{key}_sharpe": metrics.sharpe_ratio(r), f"{key}_max_drawdown": metrics.max_drawdown(r)})
    out.update({"gap_bullish": res["mean_daily_a"], "gap_bearish": res["mean_daily_b"],
                "interaction": res["mean_diff"], "ci_low": res["ci_low"], "ci_high": res["ci_high"],
                "significant": res["significant"]})
    return out


def stage_analyze() -> None:
    regime = pd.read_csv(REGIME_CSV, index_col=0, parse_dates=True)["regime"]
    fixed_m = _load(V2_CURVES / "regime_US_wf_momentum_v2.csv")
    fixed_b = _load(V2_CURVES / "regime_US_buyhold_v2.csv")
    rows = [_row("fixed 37 names (results/v2)", fixed_m["returns"], fixed_b["returns"], regime, fixed_m)]
    for label in DELISTING:
        m = _load(CURVES / f"pit_momentum_{label}.csv")
        b = _load(CURVES / f"pit_benchmark_{label}.csv")
        rows.append(_row(f"PIT S&P 500, delisting return {DELISTING[label]:+.0%}", m["returns"], b["returns"], regime, m))
    m = _load(CURVES / "pit_liquid40_momentum_base.csv")
    b = _load(CURVES / "pit_benchmark_base.csv")
    rows.append(_row("PIT S&P 500, 40 most liquid members only (vs PIT equal-weight S&P 500), delisting +0%",
                     m["returns"], b["returns"], regime, m))
    comp = pd.DataFrame(rows)
    comp.to_csv(OUT / "comparison.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 40, "display.float_format", "{:.5f}".format):
        print(comp.T.to_string())


STAGES = {"runs": stage_runs, "analyze": stage_analyze}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[1:] or list(STAGES):
        _log(f"=== stage: {name}")
        STAGES[name]()


if __name__ == "__main__":
    main()
