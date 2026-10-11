"""Performance and risk metrics computed from a daily returns series.

Every function takes a pd.Series of simple daily returns (e.g. from
Portfolio.equity_curve()["returns"]), indexed by a DatetimeIndex, and
returns a plain scalar or a small pandas/dataclass object. compute_metrics()
runs all of them and bundles the result into one PerformanceMetrics record --
that record is what tearsheet.py renders as its metrics table.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

TRADING_DAYS_PER_YEAR = 252


def _clean(returns: pd.Series) -> pd.Series:
    return returns.dropna()


def cagr(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Compound annual growth rate implied by the return series."""
    returns = _clean(returns)
    if returns.empty:
        return float("nan")
    growth = float((1.0 + returns).prod())
    if growth <= 0:
        return -1.0
    years = len(returns) / periods_per_year
    if years <= 0:
        return float("nan")
    return growth ** (1.0 / years) - 1.0


def annualized_volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Standard deviation of returns, annualised by sqrt(periods_per_year)."""
    returns = _clean(returns)
    return float(returns.std() * np.sqrt(periods_per_year))


def sharpe_ratio(
    returns: pd.Series, risk_free: float = 0.0, periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float:
    """Annualised mean excess return over its standard deviation (NaN if the series has no variance)."""
    returns = _clean(returns)
    excess = returns - risk_free / periods_per_year
    std = excess.std()
    # A constant series has a std of ~1e-18 from float noise, not 0; treat
    # anything that small as zero rather than report a Sharpe of 1e16.
    if not std or pd.isna(std) or std < 1e-12:
        return float("nan")
    return float(excess.mean() / std * np.sqrt(periods_per_year))


def sortino_ratio(
    returns: pd.Series, risk_free: float = 0.0, periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float:
    """Like Sharpe, but only penalises deviation below the target return."""
    returns = _clean(returns)
    target = risk_free / periods_per_year
    excess = returns - target
    downside = np.minimum(excess, 0.0)
    downside_deviation = float(np.sqrt(np.mean(downside ** 2)) * np.sqrt(periods_per_year))
    if not downside_deviation:
        return float("nan")
    return float(excess.mean() * periods_per_year / downside_deviation)


def _drawdown_series(returns: pd.Series) -> pd.Series:
    cumulative = (1.0 + _clean(returns)).cumprod()
    running_max = cumulative.cummax()
    return cumulative / running_max - 1.0


def max_drawdown(returns: pd.Series) -> float:
    """Worst peak-to-trough decline of the compounded series, as a negative fraction."""
    drawdown = _drawdown_series(returns)
    if drawdown.empty:
        return float("nan")
    return float(drawdown.min())


def max_drawdown_duration_days(returns: pd.Series) -> int:
    """Calendar days from the peak preceding the worst drawdown to its
    recovery, or to the last available date if it has not recovered yet."""
    returns = _clean(returns)
    if returns.empty:
        return 0

    cumulative = (1.0 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = cumulative / running_max - 1.0

    trough_idx = drawdown.idxmin()
    peak_value = running_max.loc[trough_idx]
    pre_trough = cumulative.loc[:trough_idx]
    peak_idx = pre_trough.where(pre_trough >= peak_value).last_valid_index()

    post_trough = cumulative.loc[trough_idx:]
    recovered = post_trough[post_trough >= peak_value]
    end_idx = recovered.index[0] if not recovered.empty else cumulative.index[-1]

    return int((end_idx - peak_idx).days)


def calmar_ratio(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """CAGR divided by the absolute max drawdown."""
    dd = max_drawdown(returns)
    if not dd or pd.isna(dd):
        return float("nan")
    return float(cagr(returns, periods_per_year) / abs(dd))


def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical (non-parametric) Value at Risk: the confidence-th loss percentile."""
    returns = _clean(returns)
    if returns.empty:
        return float("nan")
    return float(np.percentile(returns, (1.0 - confidence) * 100.0))


def historical_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Expected shortfall: mean return in the tail beyond the VaR threshold."""
    returns = _clean(returns)
    if returns.empty:
        return float("nan")
    threshold = historical_var(returns, confidence)
    tail = returns[returns <= threshold]
    return float(tail.mean()) if not tail.empty else threshold


def skewness(returns: pd.Series) -> float:
    """Sample skewness of the returns."""
    returns = _clean(returns)
    if len(returns) < 3:
        return float("nan")
    return float(stats.skew(returns))


def kurtosis(returns: pd.Series) -> float:
    """Excess kurtosis (0 for a normal distribution)."""
    returns = _clean(returns)
    if len(returns) < 4:
        return float("nan")
    return float(stats.kurtosis(returns))


@dataclass
class NormalityTest:
    statistic: float
    p_value: float
    is_normal_5pct: bool  # fails to reject normality at the 5% significance level


def jarque_bera_test(returns: pd.Series) -> NormalityTest:
    """Jarque-Bera normality test on the returns."""
    returns = _clean(returns)
    if len(returns) < 8:
        return NormalityTest(float("nan"), float("nan"), False)
    result = stats.jarque_bera(returns)
    return NormalityTest(
        statistic=float(result.statistic),
        p_value=float(result.pvalue),
        is_normal_5pct=bool(result.pvalue > 0.05),
    )


def win_rate(returns: pd.Series) -> float:
    """Share of non-zero-return periods with a positive return."""
    returns = _clean(returns)
    if returns.empty:
        return float("nan")
    return float((returns > 0).mean())


def best_day(returns: pd.Series) -> float:
    """Largest single-period return."""
    returns = _clean(returns)
    return float(returns.max()) if not returns.empty else float("nan")


def worst_day(returns: pd.Series) -> float:
    """Smallest single-period return."""
    returns = _clean(returns)
    return float(returns.min()) if not returns.empty else float("nan")


def monthly_returns(returns: pd.Series) -> pd.Series:
    """Compounded calendar-month returns."""
    returns = _clean(returns)
    if returns.empty:
        return returns
    return (1.0 + returns).resample("ME").prod() - 1.0


def best_month(returns: pd.Series) -> float:
    """Largest compounded calendar-month return."""
    monthly = monthly_returns(returns)
    return float(monthly.max()) if not monthly.empty else float("nan")


def worst_month(returns: pd.Series) -> float:
    """Smallest compounded calendar-month return."""
    monthly = monthly_returns(returns)
    return float(monthly.min()) if not monthly.empty else float("nan")


def yearly_returns(returns: pd.Series) -> pd.Series:
    """Compounded calendar-year returns, indexed by year."""
    returns = _clean(returns)
    if returns.empty:
        return returns
    grouped = (1.0 + returns).groupby(returns.index.year).prod() - 1.0
    grouped.index.name = "year"
    return grouped


@dataclass
class PerformanceMetrics:
    cagr: float
    annual_volatility: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    max_drawdown_duration_days: int
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    skewness: float
    kurtosis: float
    jarque_bera: NormalityTest
    win_rate: float
    best_day: float
    worst_day: float
    best_month: float
    worst_month: float
    yearly_returns: pd.Series


def compute_metrics(
    returns: pd.Series,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    risk_free: float = 0.0,
) -> PerformanceMetrics:
    """Run every metric in this module over one daily return series."""
    returns = _clean(returns)
    return PerformanceMetrics(
        cagr=cagr(returns, periods_per_year),
        annual_volatility=annualized_volatility(returns, periods_per_year),
        sharpe=sharpe_ratio(returns, risk_free, periods_per_year),
        sortino=sortino_ratio(returns, risk_free, periods_per_year),
        calmar=calmar_ratio(returns, periods_per_year),
        max_drawdown=max_drawdown(returns),
        max_drawdown_duration_days=max_drawdown_duration_days(returns),
        var_95=historical_var(returns, 0.95),
        var_99=historical_var(returns, 0.99),
        cvar_95=historical_cvar(returns, 0.95),
        cvar_99=historical_cvar(returns, 0.99),
        skewness=skewness(returns),
        kurtosis=kurtosis(returns),
        jarque_bera=jarque_bera_test(returns),
        win_rate=win_rate(returns),
        best_day=best_day(returns),
        worst_day=worst_day(returns),
        best_month=best_month(returns),
        worst_month=worst_month(returns),
        yearly_returns=yearly_returns(returns),
    )
