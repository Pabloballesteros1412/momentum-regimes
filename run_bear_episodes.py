"""US bear episodes: was momentum's 2022 protection sector composition, and is
2022 the rule or the exception? (HYPOTHESES.md H4.) Writes results/bear_episodes/.

Primary series: fixed-parameter momentum v2 (modal walk-forward choice,
in-sample) over 2005-2024, so the GFC is covered. Secondary: the v2
walk-forward replay for the post-2009 episodes. Benchmark: equal-weight buy
& hold of the same 37 names (engine v2). Attribution: daily Brinson
(allocation / selection / cash) on Yahoo sectors, summed over each episode.

    python run_bear_episodes.py
"""

from __future__ import annotations

import itertools
import json
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

import run_regimes
from quantbt.analytics import metrics
from quantbt.data.handler import DataHandler
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from quantbt.strategies.base import BuyAndHold
from quantbt.strategies.momentum import CrossSectionalMomentum, SignalCache
from quantbt.validation.replay import daily_positions, replay_walkforward

OUT = Path("results/bear_episodes")
EPISODES = {  # S&P 500 closing peak -> trough (HYPOTHESES.md H4, fixed in advance)
    "GFC": ("2007-10-09", "2009-03-09"),
    "2011": ("2011-04-29", "2011-10-03"),
    "Q4 2018": ("2018-09-20", "2018-12-24"),
    "COVID": ("2020-02-19", "2020-03-23"),
    "2022": ("2022-01-03", "2022-10-12"),
}
WARMUP = int(max(run_regimes.REDUCED_LOOKBACKS) * 7 / 5) + 30


def _single(frames, strategy, sizer):
    data = DataHandler(frames)
    pf = Portfolio(data, initial_capital=100_000.0)
    Backtest(data, strategy(data), sizer(data, pf), SimulatedBroker(data), pf).run()
    curve = pf.equity_curve()
    return curve, daily_positions(pf.fills, curve.index)


def brinson(positions: pd.DataFrame, curve: pd.DataFrame, bh_positions: pd.DataFrame, bh_curve: pd.DataFrame,
            closes: pd.DataFrame, sector: dict[str, str], start, end) -> dict:
    """Daily Brinson attribution of (momentum - B&H) over (start, end].

    Weights are end-of-day t (qty x close_t / equity_t); they earn the
    close-to-close return of day t+1. Cash earns 0.
    """
    idx = curve.index[(curve.index >= pd.Timestamp(start)) & (curve.index <= pd.Timestamp(end))]
    rets = closes.pct_change()
    rows = []
    for t0, t1 in zip(idx[:-1], idx[1:]):
        r = rets.loc[t1].fillna(0.0)
        out = {}
        for label, pos, cv in (("m", positions, curve), ("b", bh_positions, bh_curve)):
            q = pos.loc[t0].reindex(closes.columns).fillna(0.0)
            w = q * closes.loc[t0].fillna(0.0) / float(cv.loc[t0, "equity"])
            out[label] = w
        ws = {lab: out[lab].groupby(lambda s: sector.get(s, "Unknown")).sum() for lab in out}
        rs = {}
        for lab in out:
            contrib = (out[lab] * r).groupby(lambda s: sector.get(s, "Unknown")).sum()
            rs[lab] = (contrib / ws[lab].replace(0, np.nan)).fillna(0.0)
        sectors = sorted(set(ws["m"].index) | set(ws["b"].index))
        wm, wb = ws["m"].reindex(sectors).fillna(0.0), ws["b"].reindex(sectors).fillna(0.0)
        rm, rb_s = rs["m"].reindex(sectors).fillna(0.0), rs["b"].reindex(sectors).fillna(0.0)
        # A sector momentum holds but B&H doesn't can't occur here (B&H holds every name).
        rb_total = float((wb * rb_s).sum())
        alloc_s = (wm - wb) * (rb_s - rb_total)
        cash_m, cash_b = 1.0 - wm.sum(), 1.0 - wb.sum()
        rows.append({
            "date": t1,
            "allocation": float(alloc_s.sum()),
            "allocation_energy": float(alloc_s.get("Energy", 0.0)),
            "selection": float((wm * (rm - rb_s)).sum()),
            "cash": float((cash_m - cash_b) * (0.0 - rb_total)),
            "excess_actual": float(curve.loc[t1, "equity"] / curve.loc[t0, "equity"]
                                   - bh_curve.loc[t1, "equity"] / bh_curve.loc[t0, "equity"]),
            **{f"w_mom_{s}": float(wm.get(s, 0.0)) for s in sectors},
            **{f"w_bh_{s}": float(wb.get(s, 0.0)) for s in sectors},
        })
    df = pd.DataFrame(rows).set_index("date").fillna(0.0)
    res = {k: float(df[k].sum()) for k in ("allocation", "allocation_energy", "selection", "cash", "excess_actual")}
    res["residual"] = res["excess_actual"] - res["allocation"] - res["selection"] - res["cash"]
    wcols = [c for c in df.columns if c.startswith("w_")]
    res["mean_weights"] = {c: float(df[c].mean()) for c in wcols}
    return res


def episode_returns(curve: pd.DataFrame, start, end) -> dict:
    e = curve["equity"]
    seg = e[(e.index >= pd.Timestamp(start)) & (e.index <= pd.Timestamp(end))]
    r = seg.pct_change().dropna()
    return {"return": float(seg.iloc[-1] / seg.iloc[0] - 1), "max_drawdown": metrics.max_drawdown(r)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sector = dict(pd.read_csv("data/sectors_yahoo.csv")[["ticker", "sector"]].values)
    frames = DataHandler.from_yfinance(run_regimes.UNIVERSES["US"], run_regimes.START, run_regimes.END).frames
    closes = pd.DataFrame({s: df["close"] for s, df in frames.items()})
    cache = SignalCache.build(frames)
    v2 = partial(VolatilityTargetSizer, engine_version="v2")

    bh_curve, bh_pos = _single(frames, BuyAndHold, partial(EqualWeightSizer, engine_version="v2"))
    folds = pd.read_csv("results/v2/curves/regime_US_wf_momentum_v2_folds.csv")
    modal = folds[["lookback", "skip", "top_decile"]].value_counts().index[0]
    params = {"lookback": int(modal[0]), "skip": int(modal[1]), "top_decile": float(modal[2])}
    mom_curve, mom_pos = _single(frames, partial(CrossSectionalMomentum, signal_cache=cache, **params), v2)

    rows, attrib = [], {}
    for name, (s, e) in EPISODES.items():
        m, b = episode_returns(mom_curve, s, e), episode_returns(bh_curve, s, e)
        rows.append({"series": f"fixed {params}", "episode": name, "start": s, "end": e,
                     "mom_return": m["return"], "bh_return": b["return"], "excess": m["return"] - b["return"],
                     "mom_max_dd": m["max_drawdown"], "bh_max_dd": b["max_drawdown"]})
        attrib[name] = brinson(mom_pos, mom_curve, bh_pos, bh_curve, closes, sector, s, e)

    # Secondary: walk-forward v2 replay (post-2009 episodes).
    wf = replay_walkforward(frames, folds, CrossSectionalMomentum, v2, WARMUP, shared_kwargs={"signal_cache": cache})
    stored = pd.read_csv("results/v2/curves/regime_US_wf_momentum_v2.csv", index_col=0, parse_dates=True)["equity"]
    gap = wf.max_equity_gap(stored)
    wf_attrib = {}
    for name, (s, e) in EPISODES.items():
        if pd.Timestamp(s) < wf.equity_curve.index[0]:
            continue
        m, b = episode_returns(wf.equity_curve, s, e), episode_returns(bh_curve, s, e)
        rows.append({"series": "walk-forward v2 (replay)", "episode": name, "start": s, "end": e,
                     "mom_return": m["return"], "bh_return": b["return"], "excess": m["return"] - b["return"],
                     "mom_max_dd": m["max_drawdown"], "bh_max_dd": b["max_drawdown"]})
        wf_attrib[name] = brinson(wf.positions, wf.equity_curve, bh_pos, bh_curve, closes, sector, s, e)

    # Robustness: episode excess return for every grid parameter set (fixed, in-sample).
    robust = []
    for lb, sk, fr in itertools.product(run_regimes.REDUCED_LOOKBACKS, run_regimes.REDUCED_SKIPS,
                                        run_regimes.REDUCED_FRACTIONS):
        c, _ = _single(frames, partial(CrossSectionalMomentum, signal_cache=cache, lookback=lb, skip=sk,
                                       top_decile=fr), v2)
        for name, (s, e) in EPISODES.items():
            robust.append({"lookback": lb, "skip": sk, "top_decile": fr, "episode": name,
                           "excess": episode_returns(c, s, e)["return"] - episode_returns(bh_curve, s, e)["return"]})

    ep = pd.DataFrame(rows)
    ep.to_csv(OUT / "episodes.csv", index=False)
    rob = pd.DataFrame(robust)
    rob.to_csv(OUT / "episodes_param_robustness.csv", index=False)
    (OUT / "attribution_fixed.json").write_text(json.dumps(attrib, indent=2))
    (OUT / "attribution_walkforward.json").write_text(json.dumps(wf_attrib, indent=2))

    a22 = attrib["2022"]
    arith = a22["allocation"] + a22["selection"] + a22["cash"]
    h4a = {"allocation": a22["allocation"], "selection": a22["selection"], "cash": a22["cash"],
           "arithmetic_excess": arith, "allocation_share": a22["allocation"] / arith if arith else None,
           "energy_share_of_allocation": a22["allocation_energy"] / a22["allocation"] if a22["allocation"] else None}
    h4a["passes"] = bool(a22["allocation"] > 0 and arith > 0 and a22["allocation"] / arith >= 0.5)
    h4a["energy_driven"] = bool(h4a["passes"] and (h4a["energy_share_of_allocation"] or 0) >= 0.5)
    fixed = ep[ep["series"].str.startswith("fixed")].set_index("episode")
    others = [n for n in EPISODES if n != "2022"]
    k = int((fixed.loc[others, "excess"] > 0).sum())
    h4b = {"episodes_beating_bh_excl_2022": k,
           "verdict": "rule" if k >= 3 else ("mixed" if k == 2 else "exception")}
    per_param = rob[rob["episode"].isin(others)].groupby(["lookback", "skip", "top_decile"])["excess"].apply(
        lambda x: int((x > 0).sum()))
    h4b["param_sets_verdicts"] = per_param.map(lambda k: "rule" if k >= 3 else ("mixed" if k == 2 else "exception")
                                               ).value_counts().to_dict()
    h4b["param_sets_2022_beat_bh"] = int((rob[rob["episode"] == "2022"]["excess"] > 0).sum())
    summary = {"fixed_params": params, "walkforward_replay_max_rel_gap": gap, "H4a": h4a, "H4b": h4b}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    with pd.option_context("display.width", 200, "display.float_format", "{:.4f}".format):
        print(ep.to_string(index=False))
        print(pd.DataFrame({k: {x: v[x] for x in ("allocation", "allocation_energy", "selection", "cash",
                                                   "excess_actual", "residual")} for k, v in attrib.items()}).T)
        print(pd.DataFrame({k: {x: v[x] for x in ("allocation", "allocation_energy", "selection", "cash",
                                                   "excess_actual", "residual")} for k, v in wf_attrib.items()}).T)
        print(rob.pivot_table(index=["lookback", "skip", "top_decile"], columns="episode", values="excess"))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
