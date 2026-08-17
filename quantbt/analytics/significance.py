"""Statistical significance of regime-conditional performance differences.

Daily returns inside a single regime are not independent draws: regimes
cluster into contiguous runs (a bear market is many consecutive "bearish"
days, not a random scatter of them), and a strategy that only rebalances
monthly or quarterly carries its own serial correlation on top of that.
Treating every day as one independent observation overstates how much is
actually known and produces confidence intervals that are too narrow.

Two things address that here, not one:
  - `effective_sample_size` reports an autocorrelation-adjusted day count
    (n_eff <= n) as a diagnostic, so a regime with 900 calendar days but
    heavy serial correlation is not mistaken for 900 independent ones.
  - `bootstrap_regime_differences` resamples in contiguous BLOCKS (a
    moving block bootstrap), not individual days, so the resampling itself
    doesn't manufacture independence that isn't in the data.

The output flags every pairwise regime comparison as significant or not at
the given confidence level, and for the "not" cases distinguishes "the
difference could be zero" from "there isn't enough effective sample to
tell" using n_eff -- these are different findings and this module never
collapses them into one.
"""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

DEFAULT_MIN_EFFECTIVE_N = 30.0


def effective_sample_size(returns: pd.Series | np.ndarray) -> float:
    """Autocorrelation-adjusted sample size: n * (1 - rho) / (1 + rho),
    using the lag-1 sample autocorrelation rho. Clipped to [1, n]."""
    values = pd.Series(returns).dropna().to_numpy(dtype=float)
    n = len(values)
    if n < 3:
        return float(n)

    rho = np.corrcoef(values[:-1], values[1:])[0, 1]
    if np.isnan(rho):
        rho = 0.0
    rho = float(np.clip(rho, -0.99, 0.99))

    n_eff = n * (1.0 - rho) / (1.0 + rho)
    return float(np.clip(n_eff, 1.0, n))


def _block_bootstrap_means(
    values: np.ndarray, block_size: int, n_iterations: int, rng: np.random.Generator
) -> np.ndarray:
    """Moving block bootstrap: n_iterations resampled means of `values`,
    built from contiguous blocks of `block_size` (with wraparound-free
    random start positions), each resample trimmed back to len(values)."""
    n = len(values)
    if n < 2:
        return np.full(n_iterations, np.nan)

    block_size = max(1, min(block_size, n))
    n_blocks = int(np.ceil(n / block_size))
    max_start = n - block_size

    starts = rng.integers(0, max_start + 1, size=(n_iterations, n_blocks))
    offsets = np.arange(block_size)
    idx = starts[:, :, None] + offsets[None, None, :]
    idx = idx.reshape(n_iterations, -1)[:, :n]

    return values[idx].mean(axis=1)


@dataclass
class RegimeComparison:
    regime_a: str
    regime_b: str
    n_a: int
    n_b: int
    n_eff_a: float
    n_eff_b: float
    mean_daily_a: float
    mean_daily_b: float
    mean_diff: float  # daily, a - b
    ci_low: float
    ci_high: float
    significant: bool
    note: str


def bootstrap_regime_differences(
    returns: pd.Series,
    regime: pd.Series,
    regimes: list[str],
    confidence: float = 0.95,
    block_size: int = 20,
    n_iterations: int = 5000,
    min_effective_n: float = DEFAULT_MIN_EFFECTIVE_N,
    seed: int | None = 0,
) -> pd.DataFrame:
    """Every pairwise regime comparison for one daily-return series.

    For each pair of regimes, bootstraps the difference in mean daily
    return (block bootstrap, see module docstring) and reports a
    `confidence`-level CI. A pair is "significant" iff that CI excludes
    zero. Among the non-significant pairs, one whose smaller regime's
    n_eff falls under `min_effective_n` is flagged as an insufficient-
    sample result rather than a confirmed null.
    """
    aligned = pd.DataFrame({"returns": returns, "regime": regime}).dropna()
    rng = np.random.default_rng(seed)
    alpha = 1.0 - confidence

    by_regime = {label: aligned.loc[aligned["regime"] == label, "returns"].to_numpy(dtype=float) for label in regimes}
    n_eff = {label: effective_sample_size(values) for label, values in by_regime.items()}

    rows: list[RegimeComparison] = []
    for regime_a, regime_b in itertools.combinations(regimes, 2):
        values_a, values_b = by_regime[regime_a], by_regime[regime_b]

        if len(values_a) < 2 or len(values_b) < 2:
            rows.append(
                RegimeComparison(
                    regime_a, regime_b, len(values_a), len(values_b),
                    n_eff[regime_a], n_eff[regime_b],
                    float(values_a.mean()) if len(values_a) else float("nan"),
                    float(values_b.mean()) if len(values_b) else float("nan"),
                    float("nan"), float("nan"), float("nan"), False,
                    "insufficient sample -- fewer than 2 observed days in one regime",
                )
            )
            continue

        boot_diff = _block_bootstrap_means(values_a, block_size, n_iterations, rng) - _block_bootstrap_means(
            values_b, block_size, n_iterations, rng
        )
        ci_low, ci_high = np.percentile(boot_diff, [100 * alpha / 2, 100 * (1 - alpha / 2)])
        significant = bool(ci_low > 0 or ci_high < 0)

        if significant:
            note = "significant"
        elif n_eff[regime_a] < min_effective_n or n_eff[regime_b] < min_effective_n:
            note = f"not significant -- insufficient effective sample (n_eff < {min_effective_n:.0f})"
        else:
            note = "not significant -- no detectable difference at this sample size"

        rows.append(
            RegimeComparison(
                regime_a, regime_b, len(values_a), len(values_b),
                n_eff[regime_a], n_eff[regime_b],
                float(values_a.mean()), float(values_b.mean()),
                float(values_a.mean() - values_b.mean()), float(ci_low), float(ci_high),
                significant, note,
            )
        )

    return pd.DataFrame([asdict(r) for r in rows])
