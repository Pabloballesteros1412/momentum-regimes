"""Short-term reversal vs momentum vs buy & hold, by regime (PLAN.md item 2).

Everything runs on engine v2 (exit cash redeployed in the same batch), the
engine the corrected study uses. Momentum v2 and buy & hold v2 are read from
results/v2/curves/ (run_cash_v2.py); only reversal is new. Writes only under
results/reversal/.

Stages (resumable; finished reversal runs are cached under curves/):

  check    rerun buy & hold v2 for each universe on the local price cache
           and require it to equal results/v2/curves/ exactly. This is the
           drift check (PLAN.md G2): the reversal runs below must use the
           same data snapshot as the momentum runs they are compared with.
           Stops the script if it fails.
  runs     reversal walk-forward, US / Europe / Emerging 2005-2024, same
           4y/1y folds, same warm-up (so the same out-of-sample calendar as
           momentum), VolatilityTargetSizer v2, 12-combination grid:
           lookback {5, 10, 21} x skip {0, 1} x fraction {0.1, 0.2},
           monthly. Plus a cost diagnostic (single full-period backtests).
  analyze  regime breakdowns, headline metrics, invested fraction, and the
           pre-registered test family below.

Test family (fixed before any reversal result was seen), per universe, on
the days all three strategies have a return; regimes are SPY-defined:

  T1  (reversal - B&H):      bullish vs bearish            [interaction]
  T2  (reversal - B&H):      high-vol vs low-vol           [Nagel 2012 hypothesis]
  T3  (reversal - momentum): bullish vs bearish            [head-to-head interaction]
  T4  (reversal - momentum): high-vol vs low-vol           [head-to-head interaction]
  T5  (reversal - momentum): mean != 0 within each of the 4 regimes
                             (bullish_low, bullish_high, bearish_low, bearish_high)

8 tests x 3 universes = 24 tests. Moving block bootstrap (20-day blocks,
5,000 iterations, seed 0), two-sided bootstrap p-values, Holm-adjusted
across all 24 at a 5% family-wise error rate.

    python run_regimes_reversal.py            # all stages
    python run_regimes_reversal.py analyze    # one stage
"""

from __future__ import annotations

import itertools
import json
import sys
from collections import Counter
from datetime import datetime
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

from quantbt.analytics import metrics
from quantbt.analytics.regimes import REGIME_LABELS
from quantbt.analytics.significance import bootstrap_mean_test, holm_adjust
from quantbt.data.handler import DataHandler
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from quantbt.strategies.base import BuyAndHold
from quantbt.strategies.momentum import CrossSectionalMomentum, SignalCache
from quantbt.strategies.reversal import ShortTermReversal
from quantbt.validation.walkforward import run_walkforward
import run_regimes
from run_walkforward import TRADE_YEARS, TRAIN_YEARS

OUT = Path("results/reversal")
CURVES = OUT / "curves"
V2_CURVES = Path("results/v2/curves")
REGIME_CSV = Path("results/v2/spy_regime_rerun.csv")

REV_LOOKBACKS = [5, 10, 21]
REV_SKIPS = [0, 1]
REV_FRACTIONS = [0.1, 0.2]
# Same warm-up as momentum's reduced grid, so both trade the same calendar.
WARMUP_DAYS = int(max(run_regimes.REDUCED_LOOKBACKS) * 7 / 5) + 30

N_ITERATIONS, BLOCK_SIZE, CONFIDENCE, FWER = 5000, 20, 0.95, 0.05
STRATEGIES = {"reversal": "Walk-forward reversal", "momentum": "Walk-forward momentum", "buyhold": "Buy & hold"}


def _log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _grid() -> list[dict]:
    return [{"lookback": lb, "skip": sk, "top_decile": f, "rebalance_freq": "monthly"}
            for lb, sk, f in itertools.product(REV_LOOKBACKS, REV_SKIPS, REV_FRACTIONS)]


def _v2(cls):
    return partial(cls, engine_version="v2")


def _load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, index_col="date", parse_dates=["date"], float_precision="round_trip")


def _frames(universe: str):
    return DataHandler.from_yfinance(run_regimes.UNIVERSES[universe], run_regimes.START, run_regimes.END).frames


def _single(frames, strategy, sizer):
    data = DataHandler(frames)
    portfolio = Portfolio(data, initial_capital=100_000.0)
    Backtest(data, strategy(data), sizer(data, portfolio), SimulatedBroker(data), portfolio).run()
    return portfolio


# ----------------------------------------------------------------------
def stage_check() -> None:
    rows = []
    for universe in run_regimes.UNIVERSES:
        rerun = _single(_frames(universe), BuyAndHold, _v2(EqualWeightSizer)).equity_curve()["returns"]
        stored = _load(V2_CURVES / f"regime_{universe}_buyhold_v2.csv")["returns"]
        a = pd.DataFrame({"s": stored, "r": rerun}).dropna()
        rows.append({"universe": universe, "days": len(a), "stored_only": len(stored.index.difference(rerun.index)),
                     "rerun_only": len(rerun.index.difference(stored.index)),
                     "max_abs_diff": float((a["s"] - a["r"]).abs().max())})
    report = pd.DataFrame(rows)
    report["identical"] = (report["max_abs_diff"] < 1e-12) & (report["stored_only"] == 0) & (report["rerun_only"] == 0)
    report.to_csv(OUT / "data_check.csv", index=False)
    print(report.to_string(index=False))
    if not report["identical"].all():
        raise SystemExit("data check FAILED: local price cache differs from the snapshot behind results/v2 -- stopping")
    _log("data check passed: buy & hold v2 reproduces results/v2 exactly")


# ----------------------------------------------------------------------
def _cost_row(universe, label, portfolio, params) -> dict:
    curve = portfolio.equity_curve()
    years = len(curve) / 252
    avg_equity = float(curve["equity"].mean())
    return {"universe": universe, "strategy": label, "params": json.dumps(params),
            "commission_pct_per_year": portfolio.total_commission / avg_equity / years,
            "slippage_pct_per_year": portfolio.total_slippage / avg_equity / years,
            "cagr": metrics.cagr(curve["returns"]), "mean_invested": float((curve["holdings"] / curve["equity"]).mean())}


def stage_runs() -> None:
    CURVES.mkdir(parents=True, exist_ok=True)
    for universe in run_regimes.UNIVERSES:
        name = f"regime_{universe}_wf_reversal_v2"
        if (CURVES / f"{name}.csv").exists():
            continue
        frames = _frames(universe)
        wf = run_walkforward(
            frames=frames, param_grid=_grid(), strategy_factory=ShortTermReversal,
            sizer_factory=_v2(VolatilityTargetSizer), train_years=TRAIN_YEARS, trade_years=TRADE_YEARS,
            initial_capital=100_000.0, warmup_days=WARMUP_DAYS,
            trade_extra_kwargs=lambda trade_start: {"active_from": trade_start},
            strategy_shared_kwargs={"signal_cache": SignalCache.build(frames)},
            n_jobs=run_regimes.N_JOBS, progress=lambda m: _log(f"[{universe} reversal] {m}"),
        )
        pd.DataFrame([{"fold_index": i, "trade_start": f.trade_start.date(), "trade_end": f.trade_end.date(),
                       **f.params, "train_sharpe": f.train_sharpe} for i, f in enumerate(wf.folds, start=1)]
                     ).to_csv(CURVES / f"{name}_folds.csv", index=False)
        df = wf.equity_curve[["cash", "holdings", "equity", "returns"]].copy()
        df.index.name = "date"
        df["fold_start"] = df.index.isin(pd.DatetimeIndex([f.equity_curve.index[0] for f in wf.folds]))
        df.to_csv(CURVES / f"{name}.csv", float_format="%.17g")

    # Cost diagnostic: the walk-forward doesn't expose per-fold costs, so run
    # each strategy's most-chosen parameter set once over the full period.
    if not (OUT / "cost_diagnostic.csv").exists():
        rows = []
        for universe in run_regimes.UNIVERSES:
            frames = _frames(universe)
            for label, cls, folds in [("reversal", ShortTermReversal, CURVES / f"regime_{universe}_wf_reversal_v2_folds.csv"),
                                      ("momentum", CrossSectionalMomentum, V2_CURVES / f"regime_{universe}_wf_momentum_v2_folds.csv")]:
                f = pd.read_csv(folds)
                modal = Counter(tuple(r) for r in f[["lookback", "skip", "top_decile"]].itertuples(index=False)).most_common(1)[0][0]
                params = {"lookback": int(modal[0]), "skip": int(modal[1]), "top_decile": float(modal[2])}
                _log(f"[{universe}] cost diagnostic, {label} {params}")
                pf = _single(frames, partial(cls, **params), _v2(VolatilityTargetSizer))
                rows.append(_cost_row(universe, label, pf, params))
        pd.DataFrame(rows).to_csv(OUT / "cost_diagnostic.csv", index=False)


# ----------------------------------------------------------------------
def _series(universe: str) -> pd.DataFrame:
    regime = pd.read_csv(REGIME_CSV, index_col=0, parse_dates=True)["regime"]
    curves = {
        "reversal": _load(CURVES / f"regime_{universe}_wf_reversal_v2.csv"),
        "momentum": _load(V2_CURVES / f"regime_{universe}_wf_momentum_v2.csv"),
        "buyhold": _load(V2_CURVES / f"regime_{universe}_buyhold_v2.csv"),
    }
    df = pd.DataFrame({k: c["returns"] for k, c in curves.items()})
    df["regime"] = regime
    # Common out-of-sample days only (B&H starts in 2005, the walk-forwards in 2009).
    common = curves["reversal"].index.intersection(curves["momentum"].index)
    return df.loc[common].dropna(), curves


def _invested(curve: pd.DataFrame, regime: pd.Series) -> dict:
    inv = curve["holdings"] / curve["equity"]
    first = curve["fold_start"] | curve["fold_start"].shift(1, fill_value=False) if "fold_start" in curve else False
    trend = regime.reindex(inv.index)
    out = {"mean": float(inv.mean()), "share_days_below_90pct": float((inv[~first] < 0.9).mean())}
    for label in REGIME_LABELS:
        out[f"mean_{label}"] = float(inv[trend == label].mean())
    return out


def _tests(universe: str, df: pd.DataFrame) -> list[dict]:
    trend = df["regime"].str.split("_").str[0]
    vol = df["regime"].str.split("_").str[1]
    rev_bh = (df["reversal"] - df["buyhold"]).to_numpy()
    rev_mom = (df["reversal"] - df["momentum"]).to_numpy()
    kw = dict(confidence=CONFIDENCE, block_size=BLOCK_SIZE, n_iterations=N_ITERATIONS, seed=0)
    spec = [
        ("T1", "reversal - B&H", "bullish vs bearish", rev_bh[trend == "bullish"], rev_bh[trend == "bearish"]),
        ("T2", "reversal - B&H", "high vol vs low vol", rev_bh[vol == "high"], rev_bh[vol == "low"]),
        ("T3", "reversal - momentum", "bullish vs bearish", rev_mom[trend == "bullish"], rev_mom[trend == "bearish"]),
        ("T4", "reversal - momentum", "high vol vs low vol", rev_mom[vol == "high"], rev_mom[vol == "low"]),
    ] + [("T5", "reversal - momentum", f"mean in {label}", rev_mom[(df["regime"] == label).to_numpy()], None)
         for label in REGIME_LABELS]
    rows = []
    for test_id, series, contrast, a, b in spec:
        res = bootstrap_mean_test(a, b, **kw)
        rows.append({"universe": universe, "test": test_id, "series": series, "contrast": contrast,
                     "n_a": len(a), "n_b": None if b is None else len(b), **res})
    return rows


def stage_analyze() -> None:
    breakdown, headline, invested, tests = [], [], [], []
    regime = pd.read_csv(REGIME_CSV, index_col=0, parse_dates=True)["regime"]
    for universe in run_regimes.UNIVERSES:
        df, curves = _series(universe)
        for key, label in STRATEGIES.items():
            br = run_regimes.regime_breakdown(df[key], df["regime"])
            br.insert(0, "strategy", label)
            br.insert(0, "universe", universe)
            breakdown.append(br)
            r = df[key]
            headline.append({"universe": universe, "strategy": label, "start": r.index.min().date(),
                             "end": r.index.max().date(), "days": len(r),
                             "total_return": float((1 + r).prod() - 1), "cagr": metrics.cagr(r),
                             "sharpe": metrics.sharpe_ratio(r), "max_drawdown": metrics.max_drawdown(r)})
            invested.append({"universe": universe, "strategy": label,
                             **_invested(curves[key].loc[df.index], regime)})
        tests += _tests(universe, df)
        detail = df.melt(id_vars="regime", value_vars=list(STRATEGIES), var_name="strategy", value_name="return",
                         ignore_index=False).reset_index()
        detail["strategy"] = detail["strategy"].map(STRATEGIES)
        detail.insert(0, "universe", universe)
        detail.to_csv(OUT / "returns_detail.csv", mode="a" if universe != "US" else "w",
                      header=universe == "US", index=False)

    t = pd.DataFrame(tests)
    t["p_holm"] = holm_adjust(t["p_value"])
    t["significant_raw"] = t["p_value"] < 1 - CONFIDENCE
    t["significant_holm"] = t["p_holm"] < FWER
    t.to_csv(OUT / "interaction_significance.csv", index=False)
    pd.concat(breakdown, ignore_index=True).to_csv(OUT / "breakdown.csv", index=False)
    pd.DataFrame(headline).to_csv(OUT / "headline_metrics.csv", index=False)
    pd.DataFrame(invested).to_csv(OUT / "invested_fraction.csv", index=False)

    with pd.option_context("display.width", 220, "display.max_columns", 30, "display.float_format", "{:.5f}".format):
        print(pd.DataFrame(headline).to_string(index=False))
        print(pd.DataFrame(invested).to_string(index=False))
        print(pd.concat(breakdown, ignore_index=True).to_string(index=False))
        print(t.to_string(index=False))


STAGES = {"check": stage_check, "runs": stage_runs, "analyze": stage_analyze}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[1:] or list(STAGES):
        _log(f"=== stage: {name}")
        STAGES[name]()


if __name__ == "__main__":
    main()
