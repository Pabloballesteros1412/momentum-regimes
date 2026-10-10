"""Point-in-time S&P 500 rerun with the verified rename map (HYPOTHESES.md H1).

Same engine, grid, folds, warm-up and benchmark as run_regimes_pit.py; the
only change is the membership file: data/sp500_membership_intervals_renamed.csv
(build_rename_map.py), in which each renamed ticker's membership is carried
by its current ticker. Writes only to results/pit_us_renamed/;
results/pit_us/ is not touched.

    python run_pit_renamed.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import run_regimes_pit as rp
from quantbt.analytics.significance import bootstrap_regime_differences

OUT = Path("results/pit_us_renamed")
rp.OUT = OUT
rp.CURVES = OUT / "curves"
rp.INTERVALS = Path("data/sp500_membership_intervals_renamed.csv")


def coverage() -> dict:
    """Member-day coverage with the renamed membership (same definition as
    build_universe_us.py: a member-day is covered if the ticker has a Yahoo
    bar that day; reused tickers stay excluded)."""
    days = pd.DatetimeIndex(pd.read_csv(rp.REGIME_CSV, index_col=0, parse_dates=True).index).sort_values()
    excluded = set(rp.EXCLUDED.read_text().split())
    out = {}
    for label, path in (("before", Path("data/sp500_membership_intervals.csv")), ("after", rp.INTERVALS)):
        iv = pd.read_csv(path, parse_dates=["start", "end"])
        total = covered = 0
        by_year: dict[int, list[int]] = {}
        for t, g in iv.groupby("ticker"):
            mask = pd.Series(False, index=days)
            for s, e in zip(g["start"], g["end"]):
                mask |= (days >= s) & (days <= e)
            mdays = days[mask.to_numpy()]
            f = rp.CACHE / f"{t}.parquet"
            bars = pd.read_parquet(f).index if f.exists() and t not in excluded else pd.DatetimeIndex([])
            hit = mdays.isin(bars)
            total += len(mdays)
            covered += int(hit.sum())
            for y, h in pd.Series(hit, index=mdays).groupby(mdays.year):
                by_year.setdefault(int(y), [0, 0])
                by_year[int(y)][0] += len(h)
                by_year[int(y)][1] += int(h.sum())
        out[label] = {"member_days": total, "covered": covered, "coverage": covered / total,
                      "by_year": {y: c / n for y, (n, c) in sorted(by_year.items())}}
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cov = coverage()
    (OUT / "coverage.json").write_text(json.dumps(cov, indent=2))
    print(f"coverage before {cov['before']['coverage']:.4f}, after {cov['after']['coverage']:.4f}")
    rp.stage_runs()
    rp.stage_analyze()
    # H1a, exactly as registered: momentum v2 vs PIT equal weight, bull - bear.
    regime = pd.read_csv(rp.REGIME_CSV, index_col=0, parse_dates=True)["regime"]
    m = rp._load(rp.CURVES / "pit_momentum_base.csv")["returns"]
    b = rp._load(rp.CURVES / "pit_benchmark_base.csv")["returns"]
    a = pd.DataFrame({"m": m, "b": b, "regime": regime}).dropna()
    res = bootstrap_regime_differences(a["m"] - a["b"], a["regime"].str.split("_").str[0], ["bullish", "bearish"],
                                       block_size=20, n_iterations=5000, seed=0).iloc[0]
    verdict = "PASS" if (res["ci_low"] > 0) else "FAIL"
    h1 = {"estimate": res["mean_diff"], "ci_low": res["ci_low"], "ci_high": res["ci_high"], "verdict_H1a": verdict}
    (OUT / "h1_result.json").write_text(json.dumps(h1, indent=2))
    print(h1)


if __name__ == "__main__":
    main()
