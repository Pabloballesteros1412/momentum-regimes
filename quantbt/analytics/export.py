"""Pure helpers for exporting persisted results to strict, columnar JSON.

Nothing here runs a backtest: every function maps an already-persisted
series or table to plain JSON-ready Python objects. NaN/inf become None,
dates become ISO strings, so the output passes json.dumps(allow_nan=False).
"""

from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass

import numpy as np
import pandas as pd

DECIMALS = 8


def clean(value: object, decimals: int = DECIMALS) -> object:
    """One scalar -> JSON-safe value (None for NaN/inf, rounded floats)."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).date().isoformat()
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        v = float(value)
        return None if not math.isfinite(v) else round(v, decimals)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, str):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def equity_and_drawdown(returns: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Equity rebased to 1.0 at the first date, and drawdown from its running peak."""
    r = returns.fillna(0.0)
    equity = (1.0 + r).cumprod()
    equity = equity / equity.iloc[0]
    drawdown = equity / equity.cummax() - 1.0
    return equity, drawdown


def columnar(series: dict[str, pd.Series]) -> dict:
    """{name: Series} sharing an index -> {"dates": [...], name: [...]}."""
    df = pd.DataFrame(series)
    out = {"dates": [d.date().isoformat() for d in pd.DatetimeIndex(df.index)]}
    for name in df.columns:
        out[name] = [clean(v) for v in df[name].to_numpy()]
    return out


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of JSON-safe row dicts."""
    return [{k: clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def metrics_dict(m: object) -> dict:
    """compute_metrics() result -> flat JSON-safe dict (yearly returns keyed by year)."""
    d = asdict(m) if is_dataclass(m) else dict(m)
    out = {}
    for k, v in d.items():
        if k == "yearly_returns":
            out[k] = {str(pd.Timestamp(i).year): clean(x) for i, x in v.items()}
        elif k == "jarque_bera":
            out["jarque_bera_statistic"] = clean(v["statistic"])
            out["jarque_bera_p_value"] = clean(v["p_value"])
        else:
            out[k] = clean(v)
    return out
