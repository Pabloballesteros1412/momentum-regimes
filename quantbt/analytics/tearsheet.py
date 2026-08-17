"""Visual comparison tearsheet for one or more equity curves.

Renders a single PNG with five panels sharing one color per strategy
(fixed categorical order, never reassigned): equity on a log scale,
underwater drawdown, daily-return distribution with a normal overlay,
year-by-year returns, and a metrics table built from
quantbt.analytics.metrics.compute_metrics().

The whole chrome (fonts, spines, gridlines, colors) is set explicitly --
nothing here is matplotlib's out-of-the-box style.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from scipy import stats as scipy_stats

from .metrics import PerformanceMetrics, compute_metrics

# Fixed categorical order (first 3 slots of the validated 8-hue palette --
# these three clear the all-pairs CVD/normal-vision floors in both modes).
# Never reassign a slot to a different series across redraws.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

SURFACE = "#fcfcfb"
PRIMARY_INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED_INK = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

RC_PARAMS = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "font.size": 11,
    "text.color": PRIMARY_INK,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": SECONDARY_INK,
    "axes.titlecolor": PRIMARY_INK,
    "axes.titlesize": 12.5,
    "axes.titleweight": "bold",
    "xtick.color": MUTED_INK,
    "ytick.color": MUTED_INK,
    "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.grid": False,
    "legend.frameon": False,
}

_METRIC_ROWS: list[tuple[str, str, str]] = [
    ("CAGR", "cagr", "pct"),
    ("Annualized volatility", "annual_volatility", "pct"),
    ("Sharpe", "sharpe", "num"),
    ("Sortino", "sortino", "num"),
    ("Calmar", "calmar", "num"),
    ("Max drawdown", "max_drawdown", "pct"),
    ("Max DD duration (days)", "max_drawdown_duration_days", "int"),
    ("VaR 95% (daily)", "var_95", "pct"),
    ("VaR 99% (daily)", "var_99", "pct"),
    ("CVaR 95% (daily)", "cvar_95", "pct"),
    ("CVaR 99% (daily)", "cvar_99", "pct"),
    ("Skewness", "skewness", "num"),
    ("Excess kurtosis", "kurtosis", "num"),
    ("Jarque-Bera stat", "jb_stat", "num"),
    ("Jarque-Bera p-value", "jb_pvalue", "pval"),
    ("Normal at 5%?", "jb_normal", "bool"),
    ("Win rate", "win_rate", "pct"),
    ("Best day", "best_day", "pct"),
    ("Worst day", "worst_day", "pct"),
    ("Best month", "best_month", "pct"),
    ("Worst month", "worst_month", "pct"),
]


def _row_value(m: PerformanceMetrics, key: str):
    if key == "jb_stat":
        return m.jarque_bera.statistic
    if key == "jb_pvalue":
        return m.jarque_bera.p_value
    if key == "jb_normal":
        return m.jarque_bera.is_normal_5pct
    return getattr(m, key)


def _fmt(value, kind: str) -> str:
    if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
        return "n/a"
    if kind == "pct":
        return f"{value:.2%}"
    if kind == "int":
        return f"{int(value):,d}"
    if kind == "bool":
        return "yes" if value else "no"
    if kind == "pval":
        return "<0.001" if value < 0.001 else f"{value:.3f}"
    return f"{value:.2f}"


def _currency(x: float, _pos=None) -> str:
    if x >= 1_000_000:
        return f"${x / 1_000_000:.1f}M"
    if x >= 1_000:
        return f"${x / 1_000:.0f}K"
    return f"${x:.0f}"


def _style_axis(ax, y_grid: bool = True) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.spines["left"].set_linewidth(1.0)
    ax.spines["bottom"].set_linewidth(1.0)
    ax.tick_params(length=3, labelsize=9.5)
    if y_grid:
        ax.grid(axis="y", color=GRIDLINE, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)


def _date_axis(ax) -> None:
    locator = mdates.AutoDateLocator(minticks=5, maxticks=9)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))


def _plot_equity(ax, equity_curves: dict[str, pd.Series], colors: list[str]) -> None:
    for color, (label, curve) in zip(colors, equity_curves.items()):
        ax.plot(curve.index, curve.values, color=color, linewidth=2.0, solid_capstyle="round", label=label)
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(mticker.LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_currency))
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax.set_title("Equity curve (log scale)", loc="left", pad=10)
    ax.tick_params(labelbottom=False)
    _style_axis(ax)
    _date_axis(ax)


def _plot_drawdown(ax, equity_curves: dict[str, pd.Series], colors: list[str]) -> None:
    for color, (_, curve) in zip(colors, equity_curves.items()):
        drawdown = curve / curve.cummax() - 1.0
        ax.fill_between(drawdown.index, drawdown.values, 0.0, color=color, alpha=0.22, linewidth=0)
        ax.plot(drawdown.index, drawdown.values, color=color, linewidth=1.1)
    ax.axhline(0.0, color=BASELINE, linewidth=1.0)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    ax.set_title("Drawdown (underwater)", loc="left", pad=10)
    _style_axis(ax)
    _date_axis(ax)


def _plot_return_distribution(ax, returns_map: dict[str, pd.Series], colors: list[str]) -> None:
    all_values = np.concatenate([r.values for r in returns_map.values() if len(r)])
    lo, hi = np.percentile(all_values, [0.5, 99.5])
    bins = np.linspace(lo, hi, 60)

    for color, (label, returns) in zip(colors, returns_map.items()):
        ax.hist(returns, bins=bins, density=True, color=color, alpha=0.30, label=label, zorder=2)
        mu, sigma = float(returns.mean()), float(returns.std())
        if sigma > 0:
            x = np.linspace(bins[0], bins[-1], 200)
            ax.plot(x, scipy_stats.norm.pdf(x, mu, sigma), color=color, linewidth=1.6, linestyle="--", zorder=3)

    ax.axvline(0.0, color=BASELINE, linewidth=1.0, zorder=1)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    ax.set_title("Daily return distribution vs. normal", loc="left", pad=10)
    ax.set_ylabel("Density")
    _style_axis(ax)


def _plot_yearly_returns(ax, returns_map: dict[str, pd.Series], colors: list[str]) -> None:
    from .metrics import yearly_returns as _yearly

    per_label = {label: _yearly(returns) for label, returns in returns_map.items()}
    years = sorted({int(y) for series in per_label.values() for y in series.index})
    x = np.arange(len(years))
    n = len(per_label)
    width = 0.8 / max(n, 1)

    for i, (color, (label, series)) in enumerate(zip(colors, per_label.items())):
        offset = (i - (n - 1) / 2.0) * width
        values = np.array([series.get(y, np.nan) for y in years], dtype=float)
        mask = ~np.isnan(values)
        ax.bar(x[mask] + offset, values[mask], width=width * 0.9, color=color, label=label, zorder=2)

    ax.axhline(0.0, color=BASELINE, linewidth=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=0, fontsize=9)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    ax.set_title("Calendar-year returns", loc="left", pad=10)
    _style_axis(ax)


def _plot_metrics_table(ax, metrics_map: dict[str, PerformanceMetrics], colors: list[str]) -> None:
    ax.axis("off")
    labels = list(metrics_map)
    n = len(labels)
    n_rows = len(_METRIC_ROWS)

    label_x = 0.0
    col_left, col_right = 0.38, 0.995
    col_width = (col_right - col_left) / n
    col_starts = [col_left + i * col_width for i in range(n)]
    col_ends = [col_left + (i + 1) * col_width for i in range(n)]

    top, bottom = 0.97, 0.02
    row_h = (top - bottom) / (n_rows + 1)  # +1 for the header row

    header_y = top - row_h * 0.5
    for start, color, label in zip(col_starts, colors, labels):
        swatch_x = start + 0.012
        ax.scatter([swatch_x], [header_y], s=65, marker="s", color=color, transform=ax.transAxes, clip_on=False)
        ax.text(
            swatch_x + 0.018, header_y, label, transform=ax.transAxes, ha="left", va="center",
            fontsize=9.8, fontweight="bold", color=PRIMARY_INK,
        )
    ax.plot([0, 1], [top - row_h, top - row_h], transform=ax.transAxes, color=BASELINE, linewidth=1.1)

    for i, (row_label, key, kind) in enumerate(_METRIC_ROWS):
        y = top - row_h * (i + 1.5)
        if i % 2 == 0:
            ax.axhspan(y - row_h / 2, y + row_h / 2, color=GRIDLINE, alpha=0.45, transform=ax.transAxes, zorder=0)
        ax.text(label_x, y, row_label, transform=ax.transAxes, ha="left", va="center", fontsize=9.7, color=SECONDARY_INK)
        for end, label in zip(col_ends, labels):
            value = _fmt(_row_value(metrics_map[label], key), kind)
            ax.text(
                end - 0.015, y, value, transform=ax.transAxes, ha="right", va="center",
                fontsize=9.7, color=PRIMARY_INK, family="monospace",
            )


def generate_tearsheet(
    equity_curves: dict[str, pd.Series],
    output_path: str | Path,
    title: str = "Strategy Tearsheet",
    dpi: int = 220,
    risk_free: float = 0.0,
) -> None:
    """Render a comparative tearsheet PNG for one or more equity curves.

    `equity_curves` maps a strategy label to a pd.Series of equity levels
    indexed by date (e.g. Portfolio.equity_curve()["equity"]). Series may
    cover different date ranges (an out-of-sample curve starting later than
    an in-sample one is expected and plotted as-is).
    """
    if not equity_curves:
        raise ValueError("generate_tearsheet requires at least one equity curve")

    colors = SERIES_COLORS[: len(equity_curves)]
    returns_map = {label: curve.pct_change().dropna() for label, curve in equity_curves.items()}
    metrics_map = {label: compute_metrics(r, risk_free=risk_free) for label, r in returns_map.items()}

    date_min = min(curve.index.min() for curve in equity_curves.values())
    date_max = max(curve.index.max() for curve in equity_curves.values())

    with plt.rc_context(RC_PARAMS):
        fig = plt.figure(figsize=(15, 21))
        gs = fig.add_gridspec(
            nrows=4,
            ncols=2,
            height_ratios=[2.1, 1.15, 1.3, 2.3],
            left=0.08, right=0.97, top=0.90, bottom=0.03,
            hspace=0.65, wspace=0.25,
        )

        ax_equity = fig.add_subplot(gs[0, :])
        ax_dd = fig.add_subplot(gs[1, :], sharex=ax_equity)
        ax_hist = fig.add_subplot(gs[2, 0])
        ax_yearly = fig.add_subplot(gs[2, 1])
        ax_table = fig.add_subplot(gs[3, :])

        _plot_equity(ax_equity, equity_curves, colors)
        _plot_drawdown(ax_dd, equity_curves, colors)
        _plot_return_distribution(ax_hist, returns_map, colors)
        _plot_yearly_returns(ax_yearly, returns_map, colors)
        _plot_metrics_table(ax_table, metrics_map, colors)

        fig.suptitle(title, fontsize=18, fontweight="bold", color=PRIMARY_INK, x=0.08, ha="left", y=0.975)
        fig.text(
            0.08, 0.955,
            f"{date_min:%Y-%m-%d} → {date_max:%Y-%m-%d}",
            fontsize=10.5, color=SECONDARY_INK, ha="left",
        )
        ax_equity.legend(loc="upper left", ncol=1, fontsize=10.5, frameon=False)

        fig.savefig(output_path, dpi=dpi, facecolor=fig.get_facecolor())
        plt.close(fig)
