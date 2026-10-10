"""Robustness of the engine-v2 results (HYPOTHESES.md H7). Writes results/robustness_v2/.

  sweep  the 96-combination parameter grid (US, 2015-2024, single in-sample
         backtests), engine v1 and v2: how many beat buy & hold?
  costs  the US regime-study walk-forward (12-combination grid, 2005-2024,
         v2) with a flat one-way cost of 0-50 bps instead of the default
         frictions; buy & hold at the same cost; bull/bear interaction.
  mdd    paired block-bootstrap distribution of max drawdown, walk-forward
         momentum v2 vs buy & hold v2.

    python run_robustness_v2.py [sweep|costs|mdd|analyze] ...
"""

from __future__ import annotations

import itertools
import json
import sys
from datetime import datetime
from functools import partial
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

import run_momentum
import run_regimes
from quantbt.analytics import metrics
from quantbt.analytics.significance import bootstrap_regime_differences
from quantbt.data.handler import DataHandler
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import CommissionModel, SimulatedBroker, SlippageModel
from quantbt.portfolio.portfolio import Portfolio
from quantbt.risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from quantbt.strategies.base import BuyAndHold
from quantbt.strategies.momentum import CrossSectionalMomentum, SignalCache
from quantbt.validation.walkforward import run_walkforward
from run_sensitivity import FRACTIONS, FREQUENCIES, LOOKBACKS, SKIPS
from run_walkforward import TRADE_YEARS, TRAIN_YEARS

OUT = Path("results/robustness_v2")
COST_BPS = [0, 5, 10, 20, 30, 50]
WARMUP = int(max(run_regimes.REDUCED_LOOKBACKS) * 7 / 5) + 30
REGIME_CSV = Path("results/v2/spy_regime_rerun.csv")


def _log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def flat_cost_broker(data: DataHandler, bps: float) -> SimulatedBroker:
    """Broker charging exactly `bps` one-way on traded notional: no commission,
    no market impact, a spread of `bps` (the volume cap is kept)."""
    return SimulatedBroker(data, commission=CommissionModel(per_share=0.0, minimum=0.0, max_pct_of_trade=1.0),
                           slippage=SlippageModel(spread_bps=bps, impact_coefficient=0.0))


def _single(frames, strategy, sizer, broker=SimulatedBroker) -> Portfolio:
    data = DataHandler(frames)
    pf = Portfolio(data, initial_capital=100_000.0)
    Backtest(data, strategy(data), sizer(data, pf), broker(data), pf).run()
    return pf


_FRAMES = {}


def _sweep_one(args):
    lb, sk, fr, freq, version = args
    pf = _single(_FRAMES["us2015"], partial(CrossSectionalMomentum, lookback=lb, skip=sk, top_decile=fr,
                                            rebalance_freq=freq), partial(VolatilityTargetSizer, engine_version=version))
    c = pf.equity_curve()
    r = c["returns"]
    return {"lookback": lb, "skip": sk, "fraction": fr, "rebalance_freq": freq, "version": version,
            "total_return": float(c["equity"].iloc[-1] / 100_000.0 - 1), "sharpe": metrics.sharpe_ratio(r),
            "max_drawdown": metrics.max_drawdown(r), "mean_invested": float((c["holdings"] / c["equity"]).mean()),
            "friction_cost": pf.total_commission + pf.total_slippage}


def stage_sweep() -> None:
    frames = DataHandler.from_yfinance(run_momentum.TICKERS, run_momentum.START, run_momentum.END).frames
    _FRAMES["us2015"] = frames
    bh = _single(frames, BuyAndHold, partial(EqualWeightSizer, engine_version="v2")).equity_curve()
    bh_row = {"total_return": float(bh["equity"].iloc[-1] / 100_000.0 - 1), "sharpe": metrics.sharpe_ratio(bh["returns"]),
              "max_drawdown": metrics.max_drawdown(bh["returns"])}
    jobs = [(lb, sk, fr, fq, v) for v in ("v1", "v2") for lb, sk, fr, fq in
            itertools.product(LOOKBACKS, SKIPS, FRACTIONS, FREQUENCIES)]
    with Pool(run_regimes.N_JOBS) as pool:
        rows = pool.map(_sweep_one, jobs)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "sweep_96.csv", index=False)
    (OUT / "sweep_buyhold.json").write_text(json.dumps(bh_row, indent=2))
    _log(f"sweep done; B&H {bh_row}")


def stage_costs() -> None:
    frames = DataHandler.from_yfinance(run_regimes.UNIVERSES["US"], run_regimes.START, run_regimes.END).frames
    cache = SignalCache.build(frames)
    (OUT / "costs").mkdir(exist_ok=True)
    for bps in COST_BPS:
        name = OUT / "costs" / f"wf_{bps}bps.csv"
        if name.exists():
            continue
        broker = partial(flat_cost_broker, bps=bps)
        bh = _single(frames, BuyAndHold, partial(EqualWeightSizer, engine_version="v2"), broker).equity_curve()
        bh[["equity", "returns"]].rename_axis("date").to_csv(OUT / "costs" / f"bh_{bps}bps.csv")
        wf = run_walkforward(
            frames=frames, param_grid=run_regimes._param_grid(), strategy_factory=CrossSectionalMomentum,
            sizer_factory=partial(VolatilityTargetSizer, engine_version="v2"), train_years=TRAIN_YEARS,
            trade_years=TRADE_YEARS, initial_capital=100_000.0, warmup_days=WARMUP,
            trade_extra_kwargs=lambda t: {"active_from": t}, strategy_shared_kwargs={"signal_cache": cache},
            n_jobs=run_regimes.N_JOBS, progress=lambda m: _log(f"[{bps}bps] {m}"), broker_factory=broker,
        )
        wf.equity_curve[["equity", "returns"]].rename_axis("date").to_csv(name)
        pd.DataFrame([{**f.params, "trade_start": f.trade_start.date()} for f in wf.folds]).to_csv(
            OUT / "costs" / f"wf_{bps}bps_folds.csv", index=False)


def _mdd_boot(a: pd.Series, b: pd.Series, block: int, n: int = 5000, seed: int = 0) -> dict:
    d = pd.concat([a, b], axis=1, join="inner").dropna().to_numpy()
    rng = np.random.default_rng(seed)
    T = len(d)
    nb = int(np.ceil(T / block))
    out = np.empty((n, 2))
    for i in range(n):
        st = rng.integers(0, T - block + 1, size=nb)
        idx = (st[:, None] + np.arange(block)[None, :]).ravel()[:T]
        eq = np.cumprod(1 + d[idx], axis=0)
        out[i] = (eq / np.maximum.accumulate(eq, axis=0) - 1).min(axis=0)
    diff = out[:, 0] - out[:, 1]
    lo, hi = np.percentile(diff, [2.5, 97.5])
    return {"days": T, "block": block,
            "mom_mdd_point": float(metrics.max_drawdown(pd.Series(d[:, 0]))),
            "bh_mdd_point": float(metrics.max_drawdown(pd.Series(d[:, 1]))),
            "mom_mdd_p05_p50_p95": [float(x) for x in np.percentile(out[:, 0], [5, 50, 95])],
            "bh_mdd_p05_p50_p95": [float(x) for x in np.percentile(out[:, 1], [5, 50, 95])],
            "diff_ci": [float(lo), float(hi)], "p_mom_shallower": float((diff > 0).mean()),
            "reliably_shallower": bool(lo > 0)}


def stage_mdd() -> None:
    load = lambda p: pd.read_csv(p, index_col="date", parse_dates=["date"])["returns"]
    res = {}
    for study, m, b in (("US regime study 2009-2024", "results/v2/curves/regime_US_wf_momentum_v2.csv",
                         "results/v2/curves/regime_US_buyhold_v2.csv"),
                        ("US 2015-2024", "results/v2/curves/us2015_wf_momentum_v2.csv",
                         "results/v2/curves/us2015_buyhold_v2.csv")):
        mr, br = load(m), load(b)
        br = br[br.index >= mr.index.min()]
        for block in (20, 60):
            res[f"{study}, block {block}"] = _mdd_boot(mr, br, block)
    (OUT / "mdd_bootstrap.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


def stage_analyze() -> None:
    out = {}
    sw = pd.read_csv(OUT / "sweep_96.csv")
    bh = json.loads((OUT / "sweep_buyhold.json").read_text())
    pub = pd.read_csv("sensitivity_results.csv")
    out["H7a"] = {"buyhold_2015_2024": bh, "published_v1_beat_bh_total_return": int((pub["total_return"] > 12.5494).sum())}
    for v in ("v1", "v2"):
        s = sw[sw["version"] == v]
        out["H7a"][v] = {"beat_bh_total_return": int((s["total_return"] > bh["total_return"]).sum()),
                         "beat_bh_sharpe": int((s["sharpe"] > bh["sharpe"]).sum()),
                         "shallower_mdd_than_bh": int((s["max_drawdown"] > bh["max_drawdown"]).sum()),
                         "median_total_return": float(s["total_return"].median()),
                         "median_sharpe": float(s["sharpe"].median()), "mean_invested": float(s["mean_invested"].mean())}
    v1 = sw[sw["version"] == "v1"].merge(pub, on=["lookback", "skip", "fraction", "rebalance_freq"], suffixes=("", "_pub"))
    out["H7a"]["v1_rerun_vs_published_total_return_corr"] = float(v1["total_return"].corr(v1["total_return_pub"]))
    out["H7a"]["v1_rerun_vs_published_max_abs_diff"] = float((v1["total_return"] - v1["total_return_pub"]).abs().max())
    out["H7a"]["pass"] = out["H7a"]["v2"]["beat_bh_total_return"] > out["H7a"]["v1"]["beat_bh_total_return"]

    regime = pd.read_csv(REGIME_CSV, index_col=0, parse_dates=True)["regime"]
    rows = []
    for bps in COST_BPS:
        p = OUT / "costs" / f"wf_{bps}bps.csv"
        if not p.exists():
            continue
        m = pd.read_csv(p, index_col="date", parse_dates=["date"])["returns"]
        b = pd.read_csv(OUT / "costs" / f"bh_{bps}bps.csv", index_col="date", parse_dates=["date"])["returns"]
        b = b[b.index >= m.index.min()]
        a = pd.DataFrame({"m": m, "b": b, "regime": regime}).dropna()
        res = bootstrap_regime_differences(a["m"] - a["b"], a["regime"].str.split("_").str[0], ["bullish", "bearish"],
                                           block_size=20, n_iterations=5000, seed=0).iloc[0]
        rows.append({"cost_bps": bps, "mom_cagr": metrics.cagr(a["m"]), "bh_cagr": metrics.cagr(a["b"]),
                     "mom_sharpe": metrics.sharpe_ratio(a["m"]), "bh_sharpe": metrics.sharpe_ratio(a["b"]),
                     "mom_max_dd": metrics.max_drawdown(a["m"]), "interaction": res["mean_diff"],
                     "ci_low": res["ci_low"], "ci_high": res["ci_high"], "significant": bool(res["significant"])})
    costs = pd.DataFrame(rows)
    costs.to_csv(OUT / "cost_sensitivity.csv", index=False)
    if len(costs):
        gap = costs["mom_cagr"] - costs["bh_cagr"]
        out["H7b"] = {"robust_null": bool((~costs["significant"]).all()),
                      "mom_minus_bh_cagr_by_cost": dict(zip(costs["cost_bps"].astype(int), gap.round(4)))}
    if (OUT / "mdd_bootstrap.json").exists():
        out["H7c"] = json.loads((OUT / "mdd_bootstrap.json").read_text())
    (OUT / "verdict.json").write_text(json.dumps(out, indent=2, default=str))
    with pd.option_context("display.width", 220, "display.float_format", "{:.4f}".format):
        print(costs.to_string(index=False))
    print(json.dumps(out, indent=2, default=str))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    stages = {"sweep": stage_sweep, "costs": stage_costs, "mdd": stage_mdd, "analyze": stage_analyze}
    for s in sys.argv[1:] or list(stages):
        _log(f"=== {s}")
        stages[s]()


if __name__ == "__main__":
    main()
