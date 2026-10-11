"""Stress windows and tearsheet rendering on synthetic curves.

    python test_stress_tearsheet.py   (or pytest)
"""

from __future__ import annotations

import os
import tempfile

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd

from quantbt.analytics.tearsheet import generate_tearsheet
from quantbt.validation.stress import StressWindow, run_stress_test


def _curve() -> pd.Series:
    idx = pd.bdate_range("2020-01-01", "2021-12-31")
    r = np.full(len(idx), 0.003)
    r[30:40] = -0.05  # a crash in Feb 2020
    return pd.Series(100.0 * np.cumprod(1 + r), index=idx)


def test_stress_window() -> None:
    c = _curve()
    out = run_stress_test({"s": c}, [StressWindow("crash", "2020-02-01", "2020-03-31"),
                                     StressWindow("none", "1999-01-01", "1999-12-31")])
    crash = out[out["window"] == "crash"].iloc[0]
    assert crash["has_data"] and crash["max_drawdown"] < -0.35 and crash["days_to_recover"] > 0
    assert not out[out["window"] == "none"].iloc[0]["has_data"]


def test_tearsheet_renders() -> None:
    c = _curve()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.png")
        generate_tearsheet({"a": c, "b": c * 1.01}, path, title="test")
        assert os.path.getsize(path) > 10_000


if __name__ == "__main__":
    test_stress_window()
    test_tearsheet_renders()
    print("All stress/tearsheet tests passed.")
