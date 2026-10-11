"""Point-in-time S&P 500 momentum from 2000, including the dot-com bust
(HYPOTHESES.md H8). Writes only under results/pit_us_2000/ and cache/pit1996/.

Reuses build_universe_us.py and run_regimes_pit.py with their module
constants pointed at a 1996-2024 sample:
  1. SPY regimes from 1993 (classifier unchanged) -> the trading calendar.
  2. Membership 1996-2024 from the fja05680 clone (argv[1]), Yahoo prices
     from 1996, coverage report, reused-ticker exclusions.
  3. The verified rename map (data/sp500_rename_map.csv) applied.
  4. Walk-forward momentum v2 and the PIT equal-weight benchmark.
  5. H8 analysis.

    python run_pit_2000.py /path/to/fja05680-sp500-clone
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

OUT = Path("results/pit_us_2000")
DATA = OUT / "data"
START, END = "1996-01-01", "2024-12-31"
DOTCOM = ("2000-03-24", "2002-10-09")


def main() -> None:
    repo = Path(sys.argv[1])
    DATA.mkdir(parents=True, exist_ok=True)

    import run_regimes
    from quantbt.analytics.regimes import classify_regimes
    from quantbt.data.handler import DataHandler

    regime_csv = OUT / "spy_regime_1993.csv"
    if not regime_csv.exists():
        spy = DataHandler.from_yfinance(["SPY"], "1993-01-29", END).frames["SPY"]["close"]
        classify_regimes(spy)["regime"].rename("regime").to_frame().to_csv(regime_csv)
    regime = pd.read_csv(regime_csv, index_col=0, parse_dates=True)["regime"]
    cal = regime.loc[START:END]
    cal.to_frame().to_csv(OUT / "calendar_1996.csv")

    import build_universe_us as bu
    bu.START, bu.END = START, END
    bu.DATA, bu.OUT, bu.CACHE = DATA, OUT, Path("cache/pit1996")
    bu.CALENDAR = OUT / "calendar_1996.csv"
    bu.trading_days.cache_clear()
    if not (DATA / "sp500_membership_intervals.csv").exists() or not (OUT / "coverage_summary.csv").exists():
        sys.argv = [sys.argv[0], str(repo)]
        bu.main()

    # Rename map (verified on 2005-2024 member-days; pre-2005 coverage is measured, not assumed).
    rmap = dict(pd.read_csv("data/sp500_rename_map.csv")[["old", "new"]].values)
    iv = pd.read_csv(DATA / "sp500_membership_intervals.csv")
    iv["ticker"] = iv["ticker"].map(lambda t: rmap.get(t, t))
    iv.to_csv(DATA / "sp500_membership_intervals_renamed.csv", index=False)
    for new in set(rmap.values()):
        src = Path("cache/pit") / f"{new}.parquet"
        dst = bu.CACHE / f"{new}.parquet"
        if not dst.exists():  # make sure mapped targets have 1996+ prices
            import yfinance as yf
            raw = yf.download(new.replace(".", "-"), start=START, end=END, auto_adjust=True, progress=False)
            if raw is not None and not raw.empty:
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = raw.columns.get_level_values(0)
                raw.columns = [str(c).lower() for c in raw.columns]
                raw = raw[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
                raw.index.name = "timestamp"
                raw.to_parquet(dst)
            elif src.exists():
                pass

    import run_regimes_pit as rp
    run_regimes.START, run_regimes.END = START, END
    rp.OUT, rp.CURVES = OUT, OUT / "curves"
    rp.CACHE = bu.CACHE
    rp.INTERVALS = DATA / "sp500_membership_intervals_renamed.csv"
    rp.EXCLUDED = DATA / "sp500_excluded_tickers.txt"
    rp.REGIME_CSV = regime_csv
    rp.stage_runs()

    # H8 analysis
    from quantbt.analytics import metrics
    from quantbt.analytics.significance import bootstrap_regime_differences
    m = rp._load(rp.CURVES / "pit_momentum_base.csv")
    b = rp._load(rp.CURVES / "pit_benchmark_base.csv")
    a = pd.DataFrame({"m": m["returns"], "b": b["returns"], "regime": regime}).dropna()
    a = a[a.index >= m.index.min()]
    res = bootstrap_regime_differences(a["m"] - a["b"], a["regime"].str.split("_").str[0], ["bullish", "bearish"],
                                       block_size=20, n_iterations=5000, seed=0).iloc[0]

    def stats(r):
        return {"cagr": metrics.cagr(r), "sharpe": metrics.sharpe_ratio(r), "max_drawdown": metrics.max_drawdown(r),
                "total_return": float((1 + r).prod() - 1)}

    def window(curve, s, e):
        eq = curve["equity"][(curve.index >= s) & (curve.index <= e)]
        r = eq.pct_change().dropna()
        return {"return": float(eq.iloc[-1] / eq.iloc[0] - 1), "max_drawdown": metrics.max_drawdown(r)}

    cov = pd.read_csv(OUT / "coverage_by_year.csv", index_col=0)
    early = cov.loc[2000:2004]
    early_cov = float(early["covered_days"].sum() / early["member_days"].sum())
    out = {
        "coverage_2000_2004": early_cov,
        "early_unreliable": early_cov < 0.40,
        "H8a": {"interaction": res["mean_diff"], "ci_low": res["ci_low"], "ci_high": res["ci_high"],
                "gap_bullish": res["mean_daily_a"], "gap_bearish": res["mean_daily_b"],
                "pass": bool(res["ci_low"] > 0)},
        "H8b_dotcom": {"momentum": window(m, *DOTCOM), "benchmark": window(b, *DOTCOM)},
        "H8c": {"2000-2024": {"momentum": stats(a["m"]), "benchmark": stats(a["b"])},
                "2009-2024": {"momentum": stats(a["m"][a.index >= "2009-01-01"]),
                              "benchmark": stats(a["b"][a.index >= "2009-01-01"])}},
    }
    out["H8b_dotcom"]["momentum_protected"] = (out["H8b_dotcom"]["momentum"]["max_drawdown"]
                                               > out["H8b_dotcom"]["benchmark"]["max_drawdown"])
    yearly = pd.DataFrame({"momentum": metrics.yearly_returns(a["m"]), "benchmark": metrics.yearly_returns(a["b"])})
    yearly.to_csv(OUT / "yearly_returns.csv")
    (OUT / "h8_result.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
