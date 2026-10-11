"""Does idle exit cash drive the published conclusions?

Engine v1 (published) cannot spend a rebalance's exit proceeds until the
next rebalance, so the momentum book sits partly in cash. Cash does not fall
in a bear market, which could on its own manufacture some of the "drawdown
protection" the README reports. This script measures that and reruns
everything under engine v2 (quantbt.risk.sizing, engine_version="v2"),
which redeploys exit cash in the same batch.

Stages, in order (each is resumable: finished runs are cached as CSV under
results/v2/curves/ and skipped on the next invocation):

  drift    rerun buy & hold (2005-2024, three universes) and SPY regimes,
           compare against the stored regime_returns_detail.csv. Every
           v1-vs-v2 comparison below uses the RERUN v1 numbers as its
           baseline, so data drift can't pass for a v2 effect.
  runs     v1 and v2 backtests of every configuration the README reports:
             US 2015-2024: in-sample momentum, walk-forward momentum
                           (96-combo grid), buy & hold
             US / Europe / Emerging 2005-2024: walk-forward momentum
                           (12-combo grid), buy & hold
  analyze  invested fraction, headline metrics, COVID / 2022 stress
           windows, regime breakdown and regime-interaction bootstrap,
           each as published vs v1 rerun vs v2.

    python run_cash_v2.py              # all stages
    python run_cash_v2.py drift        # one stage

Writes only under results/v2/. Never touches the published CSVs, README or
tearsheet.
"""

from __future__ import annotations

import itertools
import json
import sys
from datetime import datetime
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

from quantbt.analytics import metrics
from quantbt.analytics.regimes import REGIME_LABELS, classify_regimes
from quantbt.analytics.significance import bootstrap_regime_differences
from quantbt.data.handler import DataHandler
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from quantbt.strategies.base import BuyAndHold
from quantbt.strategies.momentum import CrossSectionalMomentum, SignalCache
from quantbt.validation.stress import STRESS_WINDOWS, run_stress_test
from quantbt.validation.walkforward import run_walkforward
import run_momentum
import run_regimes
from run_sensitivity import FRACTIONS, FREQUENCIES, LOOKBACKS, SKIPS
from run_walkforward import TRADE_YEARS, TRAIN_YEARS

OUT = Path("results/v2")
CURVES = OUT / "curves"
STORED_RETURNS = Path("regime_returns_detail.csv")
STORED_INTERACTION = Path("regime_interaction_significance.csv")
STORED_BREAKDOWN = Path("regime_breakdown_partial.csv")

# v1     published engine (idle exit cash)
# v2     exit cash redeployed; vol targeting still holds cash by design when
#        the selected names' weights sum to under 100%
# v2full v2 plus long targets rescaled to 100% gross ("fully invested");
#        momentum only -- buy & hold has no such cash to remove
VERSIONS = ("v1", "v2", "v2full")
BUYHOLD_VERSIONS = ("v1", "v2")
BUYHOLD = "Buy & hold"
MOMENTUM = "Walk-forward momentum"

# README §1-2 figures (US, 2015-2024), quoted verbatim. Sharpe/Sortino are
# only in tearsheet.png, so they are reported for v1-rerun vs v2 only.
PUBLISHED_US = {
    "is_momentum": {"total_return": 5.2258, "max_drawdown": -0.2288},
    "wf_momentum": {"total_return": 1.7827, "max_drawdown": -0.3558, "calmar": 0.52, "max_dd_duration_days": 378},
    "buy_and_hold": {"total_return": 12.5494, "max_drawdown": -0.4135, "calmar": 0.72, "max_dd_duration_days": 571},
}
PUBLISHED_STRESS = {
    ("COVID crash", "wf_momentum"): {"return": -0.1820, "max_drawdown": -0.3558, "days_to_recover": 378},
    ("COVID crash", "buy_and_hold"): {"return": -0.1346, "max_drawdown": -0.3028, "days_to_recover": 107},
    ("2022 bear market", "wf_momentum"): {"return": -0.0481, "max_drawdown": -0.1824, "days_to_recover": 366},
    ("2022 bear market", "buy_and_hold"): {"return": -0.3368, "max_drawdown": -0.4015, "days_to_recover": 525},
}

# Drift tolerances: reported either way, but flagged when exceeded.
DRIFT_MIN_CORR = 0.999
DRIFT_MAX_TOTAL_RETURN_GAP = 0.02  # absolute, on cumulative return

N_ITERATIONS, BLOCK_SIZE, CONFIDENCE = 5000, 20, 0.95


def _log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ----------------------------------------------------------------------
# Backtest runners (mirror the published scripts; only the sizer differs)
# ----------------------------------------------------------------------
def _sizer(cls, version: str):
    if version == "v2full":
        return partial(cls, engine_version="v2", full_investment=True)
    return partial(cls, engine_version=version)


def _single(frames, strategy_cls, sizer_factory) -> pd.DataFrame:
    data = DataHandler(frames)
    portfolio = Portfolio(data, initial_capital=100_000.0)
    Backtest(data, strategy_cls(data), sizer_factory(data, portfolio), SimulatedBroker(data), portfolio).run()
    return portfolio.equity_curve()


def _wf_us(frames, version: str):
    """run_walkforward.py's configuration, unchanged except the sizer."""
    grid = [
        {"lookback": lb, "skip": sk, "top_decile": f, "rebalance_freq": fr}
        for lb, sk, f, fr in itertools.product(LOOKBACKS, SKIPS, FRACTIONS, FREQUENCIES)
    ]
    return run_walkforward(
        frames=frames,
        param_grid=grid,
        strategy_factory=CrossSectionalMomentum,
        sizer_factory=_sizer(VolatilityTargetSizer, version),
        train_years=TRAIN_YEARS,
        trade_years=TRADE_YEARS,
        initial_capital=100_000.0,
        warmup_days=int(max(LOOKBACKS) * 7 / 5) + 30,
        trade_extra_kwargs=lambda trade_start: {"active_from": trade_start},
        progress=lambda m: _log(f"[US 2015 {version}] {m}"),
    )


def _wf_regime(universe: str, frames, version: str):
    """run_regimes.py's configuration, unchanged except the sizer."""
    return run_walkforward(
        frames=frames,
        param_grid=run_regimes._param_grid(),
        strategy_factory=CrossSectionalMomentum,
        sizer_factory=_sizer(VolatilityTargetSizer, version),
        train_years=TRAIN_YEARS,
        trade_years=TRADE_YEARS,
        initial_capital=100_000.0,
        warmup_days=int(max(run_regimes.REDUCED_LOOKBACKS) * 7 / 5) + 30,
        trade_extra_kwargs=lambda trade_start: {"active_from": trade_start},
        strategy_shared_kwargs={"signal_cache": SignalCache.build(frames)},
        n_jobs=run_regimes.N_JOBS,
        progress=lambda m: _log(f"[{universe} {version}] {m}"),
    )


def _save_curve(name: str, curve: pd.DataFrame, fold_starts: list | None = None) -> None:
    df = curve[["cash", "holdings", "equity", "returns"]].copy()
    df.index.name = "date"
    df["fold_start"] = df.index.isin(pd.DatetimeIndex(fold_starts or []))
    df.to_csv(CURVES / f"{name}.csv", float_format="%.17g")


def _load_curve(name: str) -> pd.DataFrame:
    return pd.read_csv(CURVES / f"{name}.csv", index_col="date", parse_dates=["date"], float_precision="round_trip")


def _have(name: str) -> bool:
    return (CURVES / f"{name}.csv").exists()


def _fold_starts(wf) -> list:
    return [f.equity_curve.index[0] for f in wf.folds]


def _save_folds(name: str, wf) -> None:
    rows = [
        {"fold_index": i, "trade_start": f.trade_start.date(), "trade_end": f.trade_end.date(), **f.params,
         "train_sharpe": f.train_sharpe}
        for i, f in enumerate(wf.folds, start=1)
    ]
    pd.DataFrame(rows).to_csv(CURVES / f"{name}_folds.csv", index=False)


# ----------------------------------------------------------------------
# Stage: drift
# ----------------------------------------------------------------------
def stage_drift() -> pd.DataFrame:
    stored = pd.read_csv(STORED_RETURNS, parse_dates=["date"], float_precision="round_trip")
    rows = []

    spy = DataHandler.from_yfinance(["SPY"], run_regimes.START, run_regimes.END).frames["SPY"]["close"]
    regime = classify_regimes(spy)["regime"]
    regime.rename("regime").to_frame().to_csv(OUT / "spy_regime_rerun.csv")
    stored_regime = stored[stored["strategy"] == BUYHOLD].drop_duplicates("date").set_index("date")["regime"]
    both = pd.DataFrame({"stored": stored_regime, "rerun": regime}).dropna()
    rows.append({
        "series": "SPY regime labels", "days_compared": len(both),
        "label_agreement": float((both["stored"] == both["rerun"]).mean()),
    })

    for universe, tickers in run_regimes.UNIVERSES.items():
        name = f"regime_{universe}_buyhold_v1"
        if not _have(name):
            _log(f"[drift] rerunning buy & hold, {universe}")
            frames = DataHandler.from_yfinance(tickers, run_regimes.START, run_regimes.END).frames
            _save_curve(name, _single(frames, BuyAndHold, _sizer(EqualWeightSizer, "v1")))
        rerun = _load_curve(name)["returns"]
        old = stored[(stored["universe"] == universe) & (stored["strategy"] == BUYHOLD)].set_index("date")["return"]
        aligned = pd.DataFrame({"stored": old, "rerun": rerun}).dropna()
        diff = (aligned["rerun"] - aligned["stored"]).abs()
        tr_stored = float((1 + aligned["stored"]).prod() - 1)
        tr_rerun = float((1 + aligned["rerun"]).prod() - 1)
        corr = float(aligned["stored"].corr(aligned["rerun"]))
        rows.append({
            "series": f"{universe} buy & hold returns", "days_compared": len(aligned),
            "days_stored_only": int(old.index.difference(rerun.index).size),
            "days_rerun_only": int(rerun.index.difference(old.index).size),
            "correlation": corr, "max_abs_daily_diff": float(diff.max()),
            "days_diff_over_1bp": int((diff > 1e-4).sum()),
            "total_return_stored": tr_stored, "total_return_rerun": tr_rerun,
            "within_tolerance": bool(corr >= DRIFT_MIN_CORR and abs(tr_rerun - tr_stored) <= DRIFT_MAX_TOTAL_RETURN_GAP),
        })

    report = pd.DataFrame(rows)
    report.to_csv(OUT / "drift_check.csv", index=False)
    print(report.to_string(index=False))
    if not report.get("within_tolerance", pd.Series(dtype=bool)).dropna().all():
        _log("WARNING: drift exceeds tolerance -- v1 rerun, not the published CSVs, is the baseline below")
    return report


# ----------------------------------------------------------------------
# Stage: runs
# ----------------------------------------------------------------------
def stage_runs() -> None:
    us_frames = None
    for version in VERSIONS:
        if not _have(f"us2015_is_momentum_{version}"):
            us_frames = us_frames or DataHandler.from_yfinance(run_momentum.TICKERS, run_momentum.START, run_momentum.END).frames
            _log(f"[US 2015 {version}] in-sample momentum")
            _save_curve(f"us2015_is_momentum_{version}",
                        _single(us_frames, CrossSectionalMomentum, _sizer(VolatilityTargetSizer, version)))
        if version in BUYHOLD_VERSIONS and not _have(f"us2015_buyhold_{version}"):
            us_frames = us_frames or DataHandler.from_yfinance(run_momentum.TICKERS, run_momentum.START, run_momentum.END).frames
            _log(f"[US 2015 {version}] buy & hold")
            _save_curve(f"us2015_buyhold_{version}", _single(us_frames, BuyAndHold, _sizer(EqualWeightSizer, version)))
        if not _have(f"us2015_wf_momentum_{version}"):
            us_frames = us_frames or DataHandler.from_yfinance(run_momentum.TICKERS, run_momentum.START, run_momentum.END).frames
            wf = _wf_us(us_frames, version)
            _save_folds(f"us2015_wf_momentum_{version}", wf)
            _save_curve(f"us2015_wf_momentum_{version}", wf.equity_curve, _fold_starts(wf))

    for universe, tickers in run_regimes.UNIVERSES.items():
        frames = None
        for version in VERSIONS:
            if version in BUYHOLD_VERSIONS and not _have(f"regime_{universe}_buyhold_{version}"):
                frames = frames or DataHandler.from_yfinance(tickers, run_regimes.START, run_regimes.END).frames
                _save_curve(f"regime_{universe}_buyhold_{version}", _single(frames, BuyAndHold, _sizer(EqualWeightSizer, version)))
            if not _have(f"regime_{universe}_wf_momentum_{version}"):
                frames = frames or DataHandler.from_yfinance(tickers, run_regimes.START, run_regimes.END).frames
                wf = _wf_regime(universe, frames, version)
                _save_folds(f"regime_{universe}_wf_momentum_{version}", wf)
                _save_curve(f"regime_{universe}_wf_momentum_{version}", wf.equity_curve, _fold_starts(wf))


# ----------------------------------------------------------------------
# Stage: analyze
# ----------------------------------------------------------------------
def _regime_series() -> pd.Series:
    path = OUT / "spy_regime_rerun.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run the drift stage first")
    return pd.read_csv(path, index_col=0, parse_dates=True)["regime"]


def _invested(curve: pd.DataFrame, regime: pd.Series) -> dict:
    inv = curve["holdings"] / curve["equity"]
    trend = regime.reindex(inv.index).str.split("_").str[0]
    # Fold-start days are mechanically 0% (each fold opens in cash and buys
    # at the next open), in v1 and v2 alike; report the minimum without
    # them too so that artefact doesn't masquerade as the bug.
    first_days = curve["fold_start"] | curve["fold_start"].shift(1, fill_value=False)
    steady = inv[~first_days]
    return {
        "mean": float(inv.mean()), "min": float(inv.min()),
        "min_excl_fold_starts": float(steady.min()), "p05": float(inv.quantile(0.05)),
        "mean_bullish": float(inv[trend == "bullish"].mean()), "mean_bearish": float(inv[trend == "bearish"].mean()),
        "share_days_below_90pct": float((steady < 0.90).mean()),
    }


def _headline(curve: pd.DataFrame) -> dict:
    r = curve["returns"]
    return {
        "total_return": float(curve["equity"].iloc[-1] / curve["equity"].iloc[0] - 1.0),
        "cagr": metrics.cagr(r), "sharpe": metrics.sharpe_ratio(r), "sortino": metrics.sortino_ratio(r),
        "calmar": metrics.calmar_ratio(r), "max_drawdown": metrics.max_drawdown(r),
        "max_dd_duration_days": metrics.max_drawdown_duration_days(r),
    }


def _interaction(mom: pd.Series, bh: pd.Series, regime: pd.Series) -> dict:
    aligned = pd.DataFrame({"m": mom, "b": bh, "regime": regime}).dropna()
    diff = aligned["m"] - aligned["b"]
    trend = aligned["regime"].str.split("_").str[0]
    res = bootstrap_regime_differences(diff, trend, ["bullish", "bearish"], confidence=CONFIDENCE,
                                       block_size=BLOCK_SIZE, n_iterations=N_ITERATIONS, seed=0).iloc[0]
    return {k: res[k] for k in ("n_a", "n_b", "n_eff_b", "mean_daily_a", "mean_daily_b", "mean_diff",
                                 "ci_low", "ci_high", "significant")}


def stage_analyze() -> None:
    regime = _regime_series()
    inv_rows, head_rows, stress_rows, inter_rows, breakdown_rows = [], [], [], [], []

    # --- US 2015-2024 -------------------------------------------------
    us_curves = {}
    for key in ("is_momentum", "wf_momentum", "buy_and_hold"):
        file_key = "buyhold" if key == "buy_and_hold" else key
        for version in (BUYHOLD_VERSIONS if key == "buy_and_hold" else VERSIONS):
            c = _load_curve(f"us2015_{file_key}_{version}")
            us_curves[(key, version)] = c
            inv_rows.append({"study": "US 2015-2024", "strategy": key, "version": version, **_invested(c, regime)})
            head_rows.append({"strategy": key, "source": f"{version} rerun", **_headline(c)})
        head_rows.append({"strategy": key, "source": "published (README)", **PUBLISHED_US[key]})

    for version in VERSIONS:
        # Buy & hold is always the published-engine (v1) curve, so only the
        # momentum book changes across rows.
        stress = run_stress_test({"wf_momentum": us_curves[("wf_momentum", version)]["equity"],
                                  "buy_and_hold": us_curves[("buy_and_hold", "v1")]["equity"]},
                                 [w for w in STRESS_WINDOWS if w.name in ("COVID crash", "2022 bear market")])
        stress.insert(0, "source", f"{version} rerun")
        stress_rows.append(stress)
    pub = pd.DataFrame([{"source": "published (README)", "window": w, "strategy": s, **v}
                        for (w, s), v in PUBLISHED_STRESS.items()])
    stress_rows.append(pub)

    # --- three-universe regime study ---------------------------------
    stored = pd.read_csv(STORED_RETURNS, parse_dates=["date"], float_precision="round_trip")
    published_inter = pd.read_csv(STORED_INTERACTION).set_index("universe")
    for universe in run_regimes.UNIVERSES:
        for strategy in ("wf_momentum", "buyhold"):
            for version in (BUYHOLD_VERSIONS if strategy == "buyhold" else VERSIONS):
                c = _load_curve(f"regime_{universe}_{strategy}_{version}")
                inv_rows.append({"study": f"{universe} 2005-2024", "strategy": strategy, "version": version,
                                 **_invested(c, regime)})

        bh_v1 = _load_curve(f"regime_{universe}_buyhold_v1")["returns"]
        for version in VERSIONS:
            mom = _load_curve(f"regime_{universe}_wf_momentum_{version}")["returns"]
            # Same buy & hold (v1 rerun) for both, so only the momentum book changes.
            inter_rows.append({"universe": universe, "source": f"{version} rerun", **_interaction(mom, bh_v1, regime)})
            br = run_regimes.regime_breakdown(mom, regime)
            br.insert(0, "source", f"{version} rerun")
            br.insert(0, "universe", universe)
            breakdown_rows.append(br)
        p = published_inter.loc[universe]
        inter_rows.append({"universe": universe, "source": "published (CSV)",
                           **{k: p[k] for k in ("n_a", "n_b", "n_eff_b", "mean_daily_a", "mean_daily_b",
                                                 "mean_diff", "ci_low", "ci_high", "significant")}})
        # Sanity: the published momentum series vs our v1 rerun.
        pub_mom = stored[(stored["universe"] == universe) & (stored["strategy"] == MOMENTUM)].set_index("date")["return"]
        v1_mom = _load_curve(f"regime_{universe}_wf_momentum_v1")["returns"]
        a = pd.DataFrame({"p": pub_mom, "r": v1_mom}).dropna()
        inter_rows[-1]["v1_rerun_vs_published_corr"] = float(a["p"].corr(a["r"]))

    pd.DataFrame(inv_rows).to_csv(OUT / "invested_fraction.csv", index=False)
    pd.DataFrame(head_rows).to_csv(OUT / "headline_metrics_us2015.csv", index=False)
    pd.concat(stress_rows, ignore_index=True).to_csv(OUT / "stress_us2015.csv", index=False)
    inter = pd.DataFrame(inter_rows)
    inter.to_csv(OUT / "regime_interaction.csv", index=False)
    pd.concat(breakdown_rows, ignore_index=True).to_csv(OUT / "regime_breakdown_momentum.csv", index=False)

    # Retained share of the bullish-minus-bearish gap vs the v1 rerun. Only
    # meaningful where the v1 gap is itself clearly non-zero (the US).
    retained = {}
    for universe in run_regimes.UNIVERSES:
        sub = inter[inter["universe"] == universe].set_index("source")
        retained[universe] = {v: float(sub.loc[f"{v} rerun", "mean_diff"] / sub.loc["v1 rerun", "mean_diff"])
                              for v in ("v2", "v2full")}
    (OUT / "summary.json").write_text(json.dumps({
        "interaction_retained_share_vs_v1_rerun": retained,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }, indent=2))

    with pd.option_context("display.width", 200, "display.max_columns", 30, "display.float_format", "{:.4f}".format):
        print(pd.DataFrame(inv_rows).to_string(index=False))
        print(pd.DataFrame(head_rows).to_string(index=False))
        print(pd.concat(stress_rows, ignore_index=True).to_string(index=False))
        print(inter.to_string(index=False))
    print(json.dumps(retained, indent=2))


STAGES = {"drift": stage_drift, "runs": stage_runs, "analyze": stage_analyze}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CURVES.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[1:] or list(STAGES):
        _log(f"=== stage: {name}")
        STAGES[name]()


if __name__ == "__main__":
    main()
