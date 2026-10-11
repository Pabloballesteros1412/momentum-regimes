"""Volatility-scaled momentum vs momentum in crash windows (HYPOTHESES.md H6).

Walk-forwards (12-combination momentum grid, 2005-2024, same folds and
warm-up as the regime study, engine v2) of VolScaledMomentum at several
volatility targets, plus a like-for-like fully invested baseline
(target 10.0 = scale always 1). Writes results/volscaled/.

    python run_volscaled.py [us|pit|analyze] ...
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

import run_regimes
from quantbt.analytics import metrics
from quantbt.data.handler import DataHandler
from quantbt.data.universe import UniverseSchedule
from quantbt.strategies.momentum import SignalCache
from quantbt.strategies.volscaled import GrossTargetSizer, VolScaledMomentum
from quantbt.validation.walkforward import run_walkforward
from run_walkforward import TRADE_YEARS, TRAIN_YEARS

OUT = Path("results/volscaled")
CURVES = OUT / "curves"
WARMUP = int(max(run_regimes.REDUCED_LOOKBACKS) * 7 / 5) + 30
TARGETS = {"baseline": 10.0, "t15": 0.15, "t20": 0.20, "t25": 0.25}
WINDOWS = {"2009 rebound": ("2009-03-09", "2009-06-30"), "COVID": ("2020-02-19", "2020-06-30")}


class PITVolScaledMomentum(VolScaledMomentum):
    """VolScaledMomentum restricted to current index members."""

    def __init__(self, data, schedule: UniverseSchedule, **kwargs) -> None:
        super().__init__(data, **kwargs)
        self.schedule = schedule

    def _momentum_score(self, symbol: str) -> float | None:
        if not self.schedule.is_member(symbol, self.data.current_time):
            return None
        return super()._momentum_score(symbol)


def _log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _wf(frames, strategy, target, label, shared):
    wf = run_walkforward(
        frames=frames, param_grid=run_regimes._param_grid(), strategy_factory=partial(strategy, target_vol=target),
        sizer_factory=GrossTargetSizer, train_years=TRAIN_YEARS, trade_years=TRADE_YEARS,
        initial_capital=100_000.0, warmup_days=WARMUP, trade_extra_kwargs=lambda t: {"active_from": t},
        strategy_shared_kwargs=shared, n_jobs=run_regimes.N_JOBS, progress=lambda m: _log(f"[{label}] {m}"),
    )
    df = wf.equity_curve[["cash", "holdings", "equity", "returns"]].copy()
    df.index.name = "date"
    df.to_csv(CURVES / f"{label}.csv", float_format="%.17g")
    pd.DataFrame([{**f.params, "trade_start": f.trade_start.date(), "train_sharpe": f.train_sharpe}
                  for f in wf.folds]).to_csv(CURVES / f"{label}_folds.csv", index=False)


def stage_us(targets=TARGETS) -> None:
    frames = DataHandler.from_yfinance(run_regimes.UNIVERSES["US"], run_regimes.START, run_regimes.END).frames
    shared = {"signal_cache": SignalCache.build(frames)}
    for k, t in targets.items():
        if not (CURVES / f"us_{k}.csv").exists():
            _wf(frames, VolScaledMomentum, t, f"us_{k}", shared)


def stage_pit(targets=("baseline", "t20")) -> None:
    import run_regimes_pit as rp
    frames = rp._frames()
    schedule = UniverseSchedule.from_csv("data/sp500_membership_intervals_renamed.csv")
    shared = {"signal_cache": SignalCache.build(frames), "schedule": schedule}
    for k in targets:
        if not (CURVES / f"pit_{k}.csv").exists():
            _wf(frames, PITVolScaledMomentum, TARGETS[k], f"pit_{k}", shared)


def _load(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, index_col="date", parse_dates=["date"], float_precision="round_trip")


def _window(curve: pd.DataFrame, s, e) -> dict:
    eq = curve["equity"][(curve.index >= s) & (curve.index <= e)]
    r = eq.pct_change().dropna()
    return {"return": float(eq.iloc[-1] / eq.iloc[0] - 1), "max_drawdown": metrics.max_drawdown(r)}


def _sharpe_diff_ci(a: pd.Series, b: pd.Series, block=20, n=5000, seed=0) -> tuple[float, float, float]:
    """Paired moving block bootstrap CI for Sharpe(a) - Sharpe(b)."""
    d = pd.concat([a, b], axis=1, join="inner").dropna().to_numpy()
    rng = np.random.default_rng(seed)
    T = len(d)
    nb = int(np.ceil(T / block))
    starts = rng.integers(0, T - block + 1, size=(n, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n, -1)[:, :T]
    x = d[idx]  # n x T x 2
    sh = x.mean(axis=1) / x.std(axis=1, ddof=1) * np.sqrt(252)
    diff = sh[:, 0] - sh[:, 1]
    point = (d[:, 0].mean() / d[:, 0].std(ddof=1) - d[:, 1].mean() / d[:, 1].std(ddof=1)) * np.sqrt(252)
    lo, hi = np.percentile(diff, [2.5, 97.5])
    return float(point), float(lo), float(hi)


def stage_analyze() -> None:
    curves = {p.stem: _load(p) for p in sorted(CURVES.glob("*.csv")) if not p.stem.endswith("_folds")}
    curves["us_plain_v2"] = _load(Path("results/v2/curves/regime_US_wf_momentum_v2.csv"))
    if Path("results/pit_us_renamed/curves/pit_momentum_base.csv").exists():
        curves["pit_plain_v2"] = _load(Path("results/pit_us_renamed/curves/pit_momentum_base.csv"))
    rows = []
    for name, c in curves.items():
        r = c["returns"]
        m = metrics.monthly_returns(r)
        row = {"series": name, "cagr": metrics.cagr(r), "sharpe": metrics.sharpe_ratio(r),
               "max_drawdown": metrics.max_drawdown(r), "worst_month": float(m.min()),
               "skewness": metrics.skewness(r), "mean_invested": float((c["holdings"] / c["equity"]).mean())}
        for w, (s, e) in WINDOWS.items():
            x = _window(c, s, e)
            row[f"{w} return"], row[f"{w} max_dd"] = x["return"], x["max_drawdown"]
        rows.append(row)
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "summary.csv", index=False)
    verdict = {}
    for uni in ("us", "pit"):
        if f"{uni}_t20" not in curves or f"{uni}_baseline" not in curves:
            continue
        t = tab.set_index("series")
        h6a = {w: {"scaled": t.loc[f"{uni}_t20", f"{w} max_dd"], "baseline": t.loc[f"{uni}_baseline", f"{w} max_dd"]}
               for w in WINDOWS}
        passed = all(v["scaled"] > v["baseline"] for v in h6a.values())
        pt, lo, hi = _sharpe_diff_ci(curves[f"{uni}_t20"]["returns"], curves[f"{uni}_baseline"]["returns"])
        verdict[uni] = {"H6a": {**h6a, "pass": passed},
                        "H6b": {"sharpe_diff": pt, "ci_low": lo, "ci_high": hi, "significant": bool(lo > 0 or hi < 0)}}
    (OUT / "verdict.json").write_text(json.dumps(verdict, indent=2))
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.4f}".format):
        print(tab.to_string(index=False))
    print(json.dumps(verdict, indent=2))


def main() -> None:
    CURVES.mkdir(parents=True, exist_ok=True)
    stages = {"us": stage_us, "pit": stage_pit, "analyze": stage_analyze}
    for s in sys.argv[1:] or ["us", "analyze"]:
        _log(f"=== {s}")
        stages[s]()


if __name__ == "__main__":
    main()
