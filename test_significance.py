"""quantbt.analytics.significance: block bootstrap, n_eff, p-values, Holm.

    python test_significance.py   (or pytest)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbt.analytics.significance import (bootstrap_mean_test, bootstrap_regime_differences,
                                            effective_sample_size, holm_adjust)


def test_effective_sample_size() -> None:
    rng = np.random.default_rng(1)
    iid = rng.normal(size=4000)
    ar = np.zeros(4000)
    for t in range(1, 4000):
        ar[t] = 0.8 * ar[t - 1] + rng.normal()
    assert effective_sample_size(iid) > 3500
    assert effective_sample_size(ar) < 600  # n(1-rho)/(1+rho) ~ 4000/9


def test_regime_difference_detects_planted_effect_only() -> None:
    rng = np.random.default_rng(2)
    n = 3000
    regime = pd.Series(np.where(np.arange(n) % 400 < 300, "bull", "bear"))
    null = pd.Series(rng.normal(0, 0.01, n))
    planted = null + np.where(regime == "bull", 0.002, -0.002)
    sig = bootstrap_regime_differences(planted, regime, ["bull", "bear"], seed=0).iloc[0]
    non = bootstrap_regime_differences(null, regime, ["bull", "bear"], seed=0).iloc[0]
    assert sig["significant"] and sig["ci_low"] > 0
    assert not non["significant"]


def test_bootstrap_mean_test_pvalues() -> None:
    rng = np.random.default_rng(3)
    big = bootstrap_mean_test(rng.normal(0.01, 0.01, 2000))
    zero = bootstrap_mean_test(rng.normal(0.0, 0.01, 2000))
    assert big["p_value"] <= 1 / 5000 + 1e-12 and big["ci_low"] > 0
    assert zero["p_value"] > 0.05
    two = bootstrap_mean_test(rng.normal(0.01, 0.01, 500), rng.normal(0.0, 0.01, 500))
    assert two["ci_low"] > 0


def test_holm() -> None:
    assert np.allclose(holm_adjust([0.01, 0.04, 0.03, 0.005]), [0.03, 0.06, 0.06, 0.02])
    assert np.allclose(holm_adjust([0.5]), [0.5])
    assert (holm_adjust([0.3, 0.4, 0.9]) <= 1).all()


if __name__ == "__main__":
    test_effective_sample_size()
    test_regime_difference_detects_planted_effect_only()
    test_bootstrap_mean_test_pvalues()
    test_holm()
    print("All significance tests passed.")
