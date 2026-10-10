"""Fama-French 5 factors + momentum regressions (HYPOTHESES.md H5).

Regresses daily (US, Europe) or monthly (Emerging) excess returns of the
momentum books on the regional French factors, with Newey-West standard
errors, and reports alpha, loadings and the correlation of momentum's
active return with the academic momentum factor (UMD/WML). Factor files:
data/ff/ (unmodified copies from Kenneth French's data library).

    python run_factor_regressions.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

FF = Path("data/ff")
OUT = Path("results/factors")
V2 = Path("results/v2/curves")
FACTORS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "UMD"]
REGION_FILES = {
    "US": ("F-F_Research_Data_5_Factors_2x3_daily.csv", "F-F_Momentum_Factor_daily.csv", "daily"),
    "Europe": ("Europe_5_Factors_Daily.csv", "Europe_MOM_Factor_Daily.csv", "daily"),
    "Emerging": ("Emerging_5_Factors.csv", "Emerging_MOM_Factor.csv", "monthly"),
}
HAC_LAGS = {"daily": 10, "monthly": 3}


def read_french(path: Path) -> pd.DataFrame:
    """First table of a French CSV (header line starts with ','), in decimals."""
    lines = path.read_text(errors="ignore").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(","))
    cols = [c.strip() for c in lines[start].split(",")]
    rows = []
    for l in lines[start + 1:]:
        parts = [p.strip() for p in l.split(",")]
        if len(parts) != len(cols) or not parts[0].isdigit():
            break
        rows.append(parts)
    df = pd.DataFrame(rows, columns=["date"] + cols[1:])
    fmt = "%Y%m%d" if len(df["date"].iloc[0]) == 8 else "%Y%m"
    df["date"] = pd.to_datetime(df["date"], format=fmt)
    if fmt == "%Y%m":
        df["date"] = df["date"] + pd.offsets.MonthEnd(0)
    df = df.set_index("date").astype(float).replace(-99.99, np.nan) / 100.0
    return df


def factors(region: str) -> tuple[pd.DataFrame, str]:
    five, mom, freq = REGION_FILES[region]
    f = read_french(FF / five)
    m = read_french(FF / mom)
    m.columns = ["UMD"]  # US file calls it Mom, the others WML
    return f.join(m, how="inner"), freq


def load(path: Path) -> pd.Series:
    return pd.read_csv(path, index_col="date", parse_dates=["date"], float_precision="round_trip")["returns"]


def to_monthly(r: pd.Series) -> pd.Series:
    return (1 + r).groupby(r.index + pd.offsets.MonthEnd(0)).prod() - 1


def regress(r: pd.Series, f: pd.DataFrame, freq: str, excess: bool = True) -> dict:
    a = pd.concat([r.rename("r"), f], axis=1, join="inner").dropna()
    y = a["r"] - (a["RF"] if excess else 0.0)
    X = sm.add_constant(a[FACTORS])
    m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS[freq]})
    per_year = 252 if freq == "daily" else 12
    out = {"n": int(m.nobs), "start": a.index.min().date().isoformat(), "end": a.index.max().date().isoformat(),
           "alpha_annual": float(m.params["const"] * per_year), "alpha_t": float(m.tvalues["const"]),
           "r2": float(m.rsquared)}
    for k in FACTORS:
        out[f"b_{k}"] = float(m.params[k])
        out[f"t_{k}"] = float(m.tvalues[k])
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    series: dict[str, dict[str, pd.Series]] = {}
    for u in ("US", "Europe", "Emerging"):
        series[u] = {
            "momentum v1": load(V2 / f"regime_{u}_wf_momentum_v1.csv"),
            "momentum v2": load(V2 / f"regime_{u}_wf_momentum_v2.csv"),
            "buy & hold v2": load(V2 / f"regime_{u}_buyhold_v2.csv"),
        }
    pit = {}
    for label, d in (("PIT S&P 500 (pit_us)", "results/pit_us"), ("PIT S&P 500 renamed (pit_us_renamed)",
                                                                  "results/pit_us_renamed")):
        mp, bp = Path(d) / "curves/pit_momentum_base.csv", Path(d) / "curves/pit_benchmark_base.csv"
        if mp.exists() and bp.exists():
            pit[label] = (load(mp), load(bp))
    for label, (m, b) in pit.items():
        series["US"][f"momentum {label}"] = m
        series["US"][f"benchmark {label}"] = b

    rows, corr_rows = [], []
    for u, ss in series.items():
        f, freq = factors(u)
        common_start = ss["momentum v2"].index[ss["momentum v2"].index >= "2009-01-01"].min()
        for name, r in ss.items():
            r = r[r.index >= common_start]
            rr = to_monthly(r) if freq == "monthly" else r
            rows.append({"universe": u, "series": name, "freq": freq, **regress(rr, f, freq)})
        # Active momentum vs UMD: (momentum - its benchmark), raw (no RF).
        pairs = [("v1", ss["momentum v1"], ss["buy & hold v2"]), ("v2", ss["momentum v2"], ss["buy & hold v2"])]
        if u == "US":
            pairs += [(label, m, b) for label, (m, b) in pit.items()]
        fm = f if freq == "monthly" else None
        for label, m, b in pairs:
            act = (m - b).dropna()
            act = act[act.index >= common_start]
            d = pd.concat([act.rename("a"), f["UMD"]], axis=1, join="inner").dropna() if freq == "daily" else None
            mon = pd.concat([to_monthly(m[m.index >= common_start]) - to_monthly(b[b.index >= common_start]),
                             (f["UMD"] if freq == "monthly" else to_monthly(f["UMD"]))], axis=1, join="inner").dropna()
            mon.columns = ["a", "UMD"]
            c = float(mon["a"].corr(mon["UMD"]))
            corr_rows.append({"universe": u, "series": f"momentum {label} - benchmark",
                              "corr_daily": float(d["a"].corr(d["UMD"])) if d is not None else None,
                              "corr_monthly": c, "months": len(mon),
                              "H5b": "tracks well" if c >= 0.5 else ("tracks partly" if c >= 0.3 else "does not track"),
                              "active_regression": regress(act if freq == "daily" else to_monthly(m) - to_monthly(b),
                                                           f, freq, excess=False)})

    reg = pd.DataFrame(rows)
    reg.to_csv(OUT / "regressions.csv", index=False)
    corr = pd.DataFrame([{k: v for k, v in r.items() if k != "active_regression"} for r in corr_rows])
    corr.to_csv(OUT / "umd_correlation.csv", index=False)
    act = pd.DataFrame([{"universe": r["universe"], "series": r["series"], **r["active_regression"]} for r in corr_rows])
    act.to_csv(OUT / "active_regressions.csv", index=False)

    def get(u, s, k):
        return float(reg[(reg.universe == u) & (reg.series == s)][k].iloc[0])

    verdict = {
        "H5a_US_v2": {"b_UMD": get("US", "momentum v2", "b_UMD"), "t_UMD": get("US", "momentum v2", "t_UMD"),
                      "pass": get("US", "momentum v2", "b_UMD") > 0 and get("US", "momentum v2", "t_UMD") > 2},
        "H5d_v2_beta_exceeds_v1": {u: {"v1": get(u, "momentum v1", "b_Mkt-RF"), "v2": get(u, "momentum v2", "b_Mkt-RF")}
                                   for u in series},
    }
    verdict["H5d_v2_beta_exceeds_v1"]["pass"] = all(v["v2"] > v["v1"] for v in verdict["H5d_v2_beta_exceeds_v1"].values()
                                                    if isinstance(v, dict))
    pit_key = next((f"momentum {l}" for l in reversed(list(pit))), None)
    if pit_key:
        verdict["H5a_PIT"] = {"series": pit_key, "b_UMD": get("US", pit_key, "b_UMD"), "t_UMD": get("US", pit_key, "t_UMD"),
                              "pass": get("US", pit_key, "b_UMD") > 0 and get("US", pit_key, "t_UMD") > 2}
    (OUT / "verdict.json").write_text(json.dumps(verdict, indent=2))
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.3f}".format):
        print(reg.drop(columns=["start", "end"]).to_string(index=False))
        print(corr.to_string(index=False))
        print(act[["universe", "series", "alpha_annual", "alpha_t", "b_Mkt-RF", "b_UMD", "t_UMD", "r2"]].to_string(index=False))
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
