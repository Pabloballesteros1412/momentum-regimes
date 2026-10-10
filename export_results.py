"""Export the corrected (engine v2) results to strict JSON for a static page
(PLAN.md item 3).

Read-only over persisted results: no backtest is rerun, so nothing here can
drift or change a number. Sources:

  results/v2/curves/            momentum v2 and buy & hold v2 daily curves,
                                walk-forward folds, US 2015-2024 study
  results/v2/*.csv              v2 regime interaction, US headline + stress
  results/v2/spy_regime_rerun.csv  SPY regime per day
  results/reversal/             reversal v2 curves, folds, regime breakdown,
                                pre-registered test family

Output: web/data/v2/ (see manifest.json there for the file list). The
published v1 results are not exported here; they stay in the repo's
original CSVs.

    python export_results.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from quantbt.analytics import metrics
from quantbt.analytics.export import clean, columnar, equity_and_drawdown, metrics_dict, records
from quantbt.analytics.regimes import REGIME_LABELS

OUT = Path("web/data/v2")
SCHEMA_VERSION = 1
UNIVERSES = ["US", "Europe", "Emerging"]
V2 = Path("results/v2")
REV = Path("results/reversal")

# strategy key -> (label, curve path template, folds path template or None)
STRATEGIES = {
    "buyhold": ("Buy & hold", V2 / "curves/regime_{u}_buyhold_v2.csv", None),
    "momentum": ("Walk-forward momentum", V2 / "curves/regime_{u}_wf_momentum_v2.csv",
                 V2 / "curves/regime_{u}_wf_momentum_v2_folds.csv"),
    "reversal": ("Walk-forward reversal", REV / "curves/regime_{u}_wf_reversal_v2.csv",
                 REV / "curves/regime_{u}_wf_reversal_v2_folds.csv"),
}


def _curve(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, index_col="date", parse_dates=["date"], float_precision="round_trip")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(name: str, obj) -> Path:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, allow_nan=False, separators=(",", ":")))
    return path


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


def main() -> None:
    sources: set[Path] = set()
    regime = pd.read_csv(V2 / "spy_regime_rerun.csv", index_col=0, parse_dates=True)["regime"]
    sources.add(V2 / "spy_regime_rerun.csv")
    _write("regimes.json", {"dates": [d.date().isoformat() for d in regime.index],
                            "label": [clean(v) for v in regime.to_numpy()]})

    metric_rows, fold_rows = [], []
    for u in UNIVERSES:
        returns = {}
        for key, (label, tpl, folds_tpl) in STRATEGIES.items():
            path = Path(str(tpl).format(u=u))
            sources.add(path)
            returns[key] = _curve(path)["returns"]
            if folds_tpl is not None:
                fpath = Path(str(folds_tpl).format(u=u))
                sources.add(fpath)
                for row in records(pd.read_csv(fpath)):
                    fold_rows.append({"universe": u, "strategy": key, **row})

        common = returns["momentum"].index.intersection(returns["reversal"].index)
        series = {}
        for key, r in returns.items():
            equity, drawdown = equity_and_drawdown(r)
            series[key] = {"equity": equity, "drawdown": drawdown}
            for window, rr in (("full", r), ("common", r.loc[common])):
                metric_rows.append({"universe": u, "strategy": key, "window": window,
                                    "start": rr.index.min().date().isoformat(),
                                    "end": rr.index.max().date().isoformat(), "days": len(rr),
                                    "total_return": clean(float((1 + rr).prod() - 1)),
                                    **metrics_dict(metrics.compute_metrics(rr))})
        dates = sorted(set().union(*(r.index for r in returns.values())))
        flat = {f"{k}.{f}": s[f].reindex(dates) for k, s in series.items() for f in ("equity", "drawdown")}
        col = columnar(flat)
        _write(f"equity/{u}.json", {
            "dates": col["dates"],
            "series": {k: {f: col[f"{k}.{f}"] for f in ("equity", "drawdown")} for k in series},
        })

    _write("metrics.json", metric_rows)
    _write("folds.json", fold_rows)

    breakdown = pd.read_csv(REV / "breakdown.csv")
    sources.add(REV / "breakdown.csv")
    breakdown["strategy"] = breakdown["strategy"].map({v[0]: k for k, v in STRATEGIES.items()})
    _write("regime_metrics.json", records(breakdown))

    inter = pd.read_csv(V2 / "regime_interaction.csv")
    sources.add(V2 / "regime_interaction.csv")
    inter = inter[inter["source"] == "v2 rerun"].drop(columns=["source", "v1_rerun_vs_published_corr"], errors="ignore")
    tests = pd.read_csv(REV / "interaction_significance.csv")
    sources.add(REV / "interaction_significance.csv")
    _write("significance.json", {
        "momentum_minus_buyhold_bull_vs_bear": records(inter),
        "reversal_test_family": records(tests),
    })

    us = {}
    for name in ("headline_metrics_us2015.csv", "stress_us2015.csv"):
        df = pd.read_csv(V2 / name)
        sources.add(V2 / name)
        df = df[df["source"].isin(["v2 rerun", "v1 rerun", "published (README)"])]
        us[name.split("_us2015")[0]] = records(df)
    _write("us_2015_2024.json", us)

    files = sorted(str(p.relative_to(OUT)) for p in OUT.rglob("*.json") if p.name != "manifest.json")
    _write("manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "engine": "v2 (exit cash redeployed in the same batch; see results/v2/FINDINGS_CASH.md)",
        "files": files,
        "sources": {str(p): _sha256(p) for p in sorted(sources)},
        "universes": UNIVERSES,
        "strategies": {k: v[0] for k, v in STRATEGIES.items()},
        "regimes": REGIME_LABELS,
        "units": {"returns": "decimal (0.01 = 1%)", "dates": "ISO YYYY-MM-DD",
                  "equity": "rebased to 1.0 at each series' first date", "drawdown": "decimal, <= 0"},
        "windows": {"full": "each series' own history (B&H from 2005, walk-forwards from 2009)",
                    "common": "days both walk-forward strategies have a return (the regime tables use this)"},
        "caveats": [
            "Universes are fixed present-day ticker lists, not point-in-time (survivorship bias).",
            "No FX layer: EUR/CHF-quoted names are in local currency.",
            "SPY is the regime reference for all three universes.",
            "Engine v2; the published README numbers come from engine v1 (idle exit cash).",
        ],
    })
    print(f"wrote {len(files) + 1} files to {OUT}")


if __name__ == "__main__":
    main()
