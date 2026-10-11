"""Sector attribution of walk-forward momentum, engine v1 vs v2 (HYPOTHESES.md H3).

Replays each universe's walk-forward from its stored folds
(quantbt/validation/replay.py), checks that the replay reproduces the stored
equity curve, then measures sector composition on bearish-day rebalances.
Sectors: Yahoo Finance `sector` field, snapshot in data/sectors_yahoo.csv.
Writes results/sector_v2/.

    python run_sector_attribution.py
"""

from __future__ import annotations

import json
from datetime import date
from functools import partial
from pathlib import Path

import pandas as pd

import run_regimes
from quantbt.data.handler import DataHandler
from quantbt.risk.sizing import VolatilityTargetSizer
from quantbt.strategies.momentum import CrossSectionalMomentum, SignalCache
from quantbt.validation.replay import replay_walkforward

OUT = Path("results/sector_v2")
SECTORS = Path("data/sectors_yahoo.csv")
CURVES = Path("results/v2/curves")
REGIME_CSV = Path("results/v2/spy_regime_rerun.csv")
WARMUP = int(max(run_regimes.REDUCED_LOOKBACKS) * 7 / 5) + 30
MAX_GAP = 1e-9
PUBLISHED_V1 = {  # README §3 (share of bearish rebalances holding >= 1 name in the sector)
    ("US", "Consumer Cyclical"): 0.727, ("US", "Technology"): 0.576, ("US", "Healthcare"): 0.545,
    ("US", "Energy"): 0.273, ("Europe", "Consumer Cyclical"): 0.303, ("Europe", "Technology"): 0.182,
    ("Europe", "Healthcare"): 0.818, ("Europe", "Energy"): 0.424,
}


def sectors() -> dict[str, str]:
    if SECTORS.exists():
        df = pd.read_csv(SECTORS)
        return dict(zip(df["ticker"], df["sector"]))
    import yfinance as yf

    rows = []
    for universe, tickers in run_regimes.UNIVERSES.items():
        for t in tickers:
            try:
                s = yf.Ticker(t).info.get("sector")
            except Exception:
                s = None
            rows.append({"ticker": t, "universe": universe, "sector": s or "Unknown"})
    df = pd.DataFrame(rows).drop_duplicates("ticker")
    df["snapshot_date"] = date.today().isoformat()
    df.to_csv(SECTORS, index=False)
    return dict(zip(df["ticker"], df["sector"]))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sec = sectors()
    regime = pd.read_csv(REGIME_CSV, index_col=0, parse_dates=True)["regime"]
    trend = regime.str.split("_").str[0]

    share_rows, weight_rows, checks, conc = [], [], [], []
    for universe, tickers in run_regimes.UNIVERSES.items():
        frames = DataHandler.from_yfinance(tickers, run_regimes.START, run_regimes.END).frames
        cache = SignalCache.build(frames)
        for version in ("v1", "v2"):
            folds = pd.read_csv(CURVES / f"regime_{universe}_wf_momentum_{version}_folds.csv")
            conc.append({"universe": universe, "version": version,
                         "share_folds_top10pct": float((folds["top_decile"] == 0.1).mean())})
            r = replay_walkforward(frames, folds, CrossSectionalMomentum,
                                   partial(VolatilityTargetSizer, engine_version=version), WARMUP,
                                   shared_kwargs={"signal_cache": cache})
            stored = pd.read_csv(CURVES / f"regime_{universe}_wf_momentum_{version}.csv", index_col=0,
                                 parse_dates=True)["equity"]
            gap = r.max_equity_gap(stored)
            checks.append({"universe": universe, "version": version, "max_rel_equity_gap": gap,
                           "replay_ok": gap < MAX_GAP, "rebalances": len(r.rebalances)})
            if gap >= MAX_GAP:
                continue
            for subset in ("bearish", "all"):
                days = [d for d in r.rebalances if subset == "all" or trend.get(d) == "bearish"]
                sel_rows = [{sec.get(x, "Unknown"): 1.0 for x in r.selections[d]} for d in days]
                sel = pd.DataFrame(sel_rows).fillna(0.0)
                held_rows = []
                for d in days:
                    hv = r.holdings_value[d]
                    total = sum(hv.values()) or 1.0
                    by_sector: dict[str, float] = {}
                    for s, v in hv.items():
                        by_sector[sec.get(s, "Unknown")] = by_sector.get(sec.get(s, "Unknown"), 0.0) + v / total
                    held_rows.append(by_sector)
                df = pd.DataFrame(held_rows).fillna(0.0)
                for s in sorted(df.columns):
                    share_rows.append({"universe": universe, "version": version, "rebalances": subset,
                                       "n_rebalances": len(days), "sector": s,
                                       "share_holding": float((df[s] > 0).mean()),
                                       "share_selected": float((sel[s] > 0).mean()) if s in sel else 0.0,
                                       "mean_value_weight": float(df[s].mean())})

    shares = pd.DataFrame(share_rows)
    shares.to_csv(OUT / "sector_shares.csv", index=False)
    pd.DataFrame(checks).to_csv(OUT / "replay_check.csv", index=False)
    pd.DataFrame(conc).to_csv(OUT / "concentration.csv", index=False)

    bear = shares[shares["rebalances"] == "bearish"].set_index(["universe", "version", "sector"])["share_holding"]
    bear_sel = shares[shares["rebalances"] == "bearish"].set_index(["universe", "version", "sector"])["share_selected"]

    def g(u, v, s):
        return float(bear.get((u, v, s), 0.0))

    method = [{"universe": u, "sector": s, "published_v1": p, "replay_v1_held": g(u, "v1", s),
               "replay_v1_selected": float(bear_sel.get((u, "v1", s), 0.0))}
              for (u, s), p in PUBLISHED_V1.items()]
    pd.DataFrame(method).to_csv(OUT / "method_check_v1.csv", index=False)
    verdict = {}
    for version in ("v1", "v2"):
        orderings = {
            "US > Europe, Consumer Cyclical": g("US", version, "Consumer Cyclical") > g("Europe", version, "Consumer Cyclical"),
            "US > Europe, Technology": g("US", version, "Technology") > g("Europe", version, "Technology"),
            "Europe > US, Healthcare": g("Europe", version, "Healthcare") > g("US", version, "Healthcare"),
            "Europe > US, Energy": g("Europe", version, "Energy") > g("US", version, "Energy"),
        }
        n = sum(orderings.values())
        verdict[version] = {"orderings": orderings, "n_hold": n,
                            "verdict": "holds" if n == 4 else ("partly holds" if n >= 2 else "does not hold")}
    (OUT / "verdict.json").write_text(json.dumps(verdict, indent=2))
    print(pd.DataFrame(checks).to_string(index=False))
    print(pd.DataFrame(method).to_string(index=False))
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
