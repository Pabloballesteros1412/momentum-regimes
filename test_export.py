"""The JSON export (web/data/v2/, export_results.py) matches the CSVs it was
built from.

    python export_results.py && python test_export.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from quantbt.analytics import metrics
from quantbt.analytics.export import clean, equity_and_drawdown
import run_regimes

OUT = Path("web/data/v2")
V2 = Path("results/v2")
REV = Path("results/reversal")
TOL = 1e-8  # the export rounds to 8 decimals


def _strict(path: Path):
    def bad(token):
        raise ValueError(f"{path}: non-strict JSON constant {token}")
    return json.loads(path.read_text(), parse_constant=bad)


def _curve(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, index_col="date", parse_dates=["date"], float_precision="round_trip")


def test_strict_json_and_manifest() -> None:
    manifest = _strict(OUT / "manifest.json")
    for name in manifest["files"]:
        _strict(OUT / name)
    for src, digest in manifest["sources"].items():
        assert hashlib.sha256(Path(src).read_bytes()).hexdigest() == digest, f"{src} changed since export"
    print(f"{len(manifest['files']) + 1} files parse as strict JSON; {len(manifest['sources'])} source hashes match.")


def test_regime_metrics_match_breakdown_csv() -> None:
    exported = pd.DataFrame(_strict(OUT / "regime_metrics.json"))
    csv = pd.read_csv(REV / "breakdown.csv")
    assert len(exported) == len(csv)
    for col in ("annual_return", "annual_vol", "max_drawdown", "sharpe"):
        assert np.allclose(exported[col].astype(float), csv[col], atol=TOL, equal_nan=True), col
    print("regime_metrics.json equals results/reversal/breakdown.csv.")


def test_breakdown_rebuilds_from_daily_returns() -> None:
    """Consistency between two persisted files: per-regime CAGR rebuilt from
    returns_detail.csv equals breakdown.csv."""
    detail = pd.read_csv(REV / "returns_detail.csv", parse_dates=["date"])
    csv = pd.read_csv(REV / "breakdown.csv").set_index(["universe", "strategy", "regime"])
    n = 0
    for (u, s, r), g in detail.dropna(subset=["regime"]).groupby(["universe", "strategy", "regime"]):
        assert abs(metrics.cagr(g.set_index("date")["return"]) - csv.loc[(u, s, r), "annual_return"]) < 1e-12
        n += 1
    print(f"{n} per-regime CAGRs rebuilt from returns_detail.csv match breakdown.csv.")


def test_equity_and_metrics_match_curves() -> None:
    m = pd.DataFrame(_strict(OUT / "metrics.json")).set_index(["universe", "strategy", "window"])
    head = pd.read_csv(REV / "headline_metrics.csv")
    label = {"Buy & hold": "buyhold", "Walk-forward momentum": "momentum", "Walk-forward reversal": "reversal"}
    for _, row in head.iterrows():
        key = (row["universe"], label[row["strategy"]], "common")
        assert abs(m.loc[key, "total_return"] - row["total_return"]) < TOL * 10, key
        assert abs(m.loc[key, "sharpe"] - row["sharpe"]) < TOL * 10, key
        assert abs(m.loc[key, "max_drawdown"] - row["max_drawdown"]) < TOL * 10, key
    for u in run_regimes.UNIVERSES:
        eq = _strict(OUT / f"equity/{u}.json")
        for key, path in (("buyhold", V2 / f"curves/regime_{u}_buyhold_v2.csv"),
                          ("momentum", V2 / f"curves/regime_{u}_wf_momentum_v2.csv"),
                          ("reversal", REV / f"curves/regime_{u}_wf_reversal_v2.csv")):
            curve = _curve(path)
            series = pd.Series(eq["series"][key]["equity"], index=pd.to_datetime(eq["dates"])).dropna()
            expected = curve["equity"] / curve["equity"].iloc[0]
            assert np.allclose(series.reindex(expected.index), expected, rtol=1e-7), (u, key)
            dd = pd.Series(eq["series"][key]["drawdown"], index=pd.to_datetime(eq["dates"])).dropna()
            assert abs(dd.min() - m.loc[(u, key, "full"), "max_drawdown"]) < 1e-7, (u, key)
    print("Rebased equity curves and their drawdowns match the stored curves; common-window metrics match "
          "headline_metrics.csv.")


def test_significance_matches_csvs() -> None:
    sig = _strict(OUT / "significance.json")
    tests = pd.DataFrame(sig["reversal_test_family"])
    csv = pd.read_csv(REV / "interaction_significance.csv")
    for col in ("estimate", "ci_low", "ci_high", "p_value", "p_holm"):
        assert np.allclose(tests[col].astype(float), csv[col], atol=TOL), col
    assert (tests["significant_holm"] == csv["significant_holm"]).all()
    inter = pd.DataFrame(sig["momentum_minus_buyhold_bull_vs_bear"])
    v2 = pd.read_csv(V2 / "regime_interaction.csv")
    v2 = v2[v2["source"] == "v2 rerun"].reset_index(drop=True)
    for col in ("mean_diff", "ci_low", "ci_high"):
        assert np.allclose(inter[col].astype(float), v2[col], atol=TOL), col
    print("significance.json equals interaction_significance.csv and the v2 rows of regime_interaction.csv.")


def test_folds_match_csvs() -> None:
    folds = pd.DataFrame(_strict(OUT / "folds.json"))
    for u in run_regimes.UNIVERSES:
        for key, path in (("momentum", V2 / f"curves/regime_{u}_wf_momentum_v2_folds.csv"),
                          ("reversal", REV / f"curves/regime_{u}_wf_reversal_v2_folds.csv")):
            csv = pd.read_csv(path)
            got = folds[(folds["universe"] == u) & (folds["strategy"] == key)].reset_index(drop=True)
            assert len(got) == len(csv) == 16, (u, key)
            assert (got["lookback"].astype(int) == csv["lookback"]).all()
            assert np.allclose(got["train_sharpe"].astype(float), csv["train_sharpe"], atol=TOL)
    print("folds.json equals the fold CSVs (16 folds per universe and strategy).")


def test_clean_is_strict() -> None:
    assert clean(float("nan")) is None and clean(float("inf")) is None and clean(np.float64(1.5)) == 1.5
    eq, dd = equity_and_drawdown(pd.Series([0.1, -0.5, 0.2]))
    assert eq.iloc[0] == 1.0 and abs(dd.min() - (-0.5)) < 1e-12
    print("clean() maps NaN/inf to null; equity is rebased to 1.0.")


if __name__ == "__main__":
    test_clean_is_strict()
    test_strict_json_and_manifest()
    test_regime_metrics_match_breakdown_csv()
    test_breakdown_rebuilds_from_daily_returns()
    test_equity_and_metrics_match_curves()
    test_significance_matches_csvs()
    test_folds_match_csvs()
    print("\nAll export tests passed.")
