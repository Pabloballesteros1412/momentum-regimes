"""Regime-conditional performance across three universes (US, Europe,
Emerging Markets), 2005-2024, broken down by SPY-defined market regime
(quantbt.analytics.regimes). SPY is used as a single, shared regime
reference for all three universes -- this asks "how did each universe's
strategies perform when *global* market conditions were in regime X",
not "what was each region's own local regime", which keeps the three
universes directly comparable against one consistent yardstick.

CURRENCY NOTE
--------------------------------------------------------------------------
The engine has no FX layer: `Portfolio.cash` is one unhedged number and
every price is used as-is. Mixing tickers quoted in wildly different units
into that one pool would silently break position sizing -- a GBX
(pence-quoted) London listing is ~100x a comparable USD price, a DKK
listing ~7x -- so the EU universe below deliberately prefers a USD-quoted
NYSE/NASDAQ ADR wherever a European blue chip has a liquid one (SAP, NVS,
NVO, AZN, SNY, SHEL, BP, HSBC, DEO, BTI, RIO, UL, VOD, ING, TTE, E, RACE,
GSK, ASML, UBS all confirmed USD via yfinance's own `currency` field), and
falls back to EUR or CHF local listings for the rest -- both are within
roughly 1.0-1.4x USD over this period, an order-of-magnitude-correct
approximation, not a rigorously FX-hedged one. All Emerging-Markets names
are USD-denominated ADRs for the same reason (also confirmed via
`currency`). This is a real simplification, not a rounding error hidden
under the rug: returns for EUR/CHF-quoted names are this backtest's local
nominal return, not what a USD-based investor would have realized after
translating currency exposure.

SURVIVORSHIP / POINT-IN-TIME WARNING -- all three universes
--------------------------------------------------------------------------
Every ticker list below is a FIXED, PRESENT-DAY selection, exactly like
run_momentum.py's US universe -- none of them are point-in-time
constituent lists for their respective benchmarks (STOXX 600, or any EM
index). Every name here is one already known to have stayed listed,
liquid, and (for the EM ADRs) un-sanctioned through 2025. Names that would
otherwise be obvious large-cap inclusions were dropped for exactly the
opposite reason during construction: several Chinese state-owned oil and
telecom ADRs (PetroChina, Sinopec, China Mobile, China Telecom, China
Unicom) were delisted from the NYSE in 2021 under a U.S. executive order
and are gone from Yahoo's ADR listings; Tata Motors' and Embraer's ADRs
failed this project's own download check (see the ticker-verification
step in the project history) and were dropped rather than debugged. Both
are small, concrete demonstrations of the bias this warning is about: the
investable universe visible *today* already excludes names a real 2005
investor could have owned, in both directions (delisted for market
reasons, delisted for geopolitical ones). The walk-forward engine's
train/trade split is careful about *time* -- a fold never sees its own
future -- but every fold still trades from this same fixed 2025-vintage
list, including early folds whose training window predates the IPOs of
several constituents (Alibaba: 2014, JD.com: 2014, PDD: 2021), so those
names simply cannot appear in the effective universe until the underlying
data does.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import itertools
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from quantbt.analytics import metrics
from quantbt.analytics.regimes import REGIME_LABELS, classify_regimes
from quantbt.data.handler import DataHandler
from quantbt.engine.backtest import Backtest
from quantbt.engine.broker import SimulatedBroker
from quantbt.portfolio.portfolio import Portfolio
from quantbt.risk.sizing import EqualWeightSizer, VolatilityTargetSizer
from quantbt.strategies.base import BuyAndHold
from quantbt.strategies.momentum import CrossSectionalMomentum, SignalCache
from quantbt.validation.walkforward import run_walkforward
from run_momentum import TICKERS as US_TICKERS
from run_walkforward import TRADE_YEARS, TRAIN_YEARS

START = "2005-01-01"
END = "2024-12-31"

N_JOBS = max(1, (os.cpu_count() or 2) - 1)

FOLDS_CSV = Path("regime_folds_partial.csv")
BREAKDOWN_CSV = Path("regime_breakdown_partial.csv")
RETURNS_CSV = Path("regime_returns_detail.csv")  # per-day (universe, strategy, return, regime); feeds run_significance.py

# USD-ADR-first, EUR/CHF-local fallback -- see the CURRENCY NOTE above.
EUROPE_TICKERS = [
    "SAP", "NVS", "NVO", "AZN", "SNY", "SHEL", "BP", "HSBC", "DEO", "BTI",
    "RIO", "UL", "VOD", "ING", "TTE", "E", "RACE", "GSK", "ASML", "UBS",
    "MC.PA", "OR.PA", "AI.PA", "BNP.PA", "SU.PA", "DG.PA", "EL.PA",
    "SIE.DE", "ALV.DE", "DTE.DE", "BAS.DE", "BMW.DE", "MBG.DE",
    "HEIA.AS", "NESN.SW", "ZURN.SW", "ISP.MI", "ENEL.MI",
]

# All confirmed USD-denominated ADRs -- see the CURRENCY NOTE above.
EMERGING_TICKERS = [
    "TSM", "INFY", "IBN", "HDB", "WIT", "RDY",
    "VALE", "PBR", "ITUB", "BBD", "ABEV", "SID", "GGB", "SBS", "CIG",
    "AMX", "BSAC", "CCU", "CIB", "EC", "BAP",
    "SSL", "AU", "HMY", "GFI",
    "SKM", "PKX", "KB", "WF",
    "TKC", "CHT", "UMC",
    "MELI", "NTES", "BABA", "JD", "PDD",
]

UNIVERSES: dict[str, list[str]] = {
    "US": US_TICKERS,
    "Europe": EUROPE_TICKERS,
    "Emerging": EMERGING_TICKERS,
}

# Reduced grid: lookback x skip x fraction only (12 combos), rebalance_freq
# held fixed at the strategy's own default ("monthly") rather than swept.
REDUCED_LOOKBACKS = [189, 252, 315]
REDUCED_SKIPS = [10, 21]
REDUCED_FRACTIONS = [0.1, 0.2]


def _param_grid() -> list[dict]:
    return [
        {"lookback": lookback, "skip": skip, "top_decile": fraction, "rebalance_freq": "monthly"}
        for lookback, skip, fraction in itertools.product(REDUCED_LOOKBACKS, REDUCED_SKIPS, REDUCED_FRACTIONS)
    ]


def _log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def _append_csv(path: Path, row: dict) -> None:
    """Append one row, writing the header only if the file doesn't exist yet."""
    df = pd.DataFrame([row])
    df.to_csv(path, mode="a", header=not path.exists(), index=False)


def _append_returns_detail(universe_name: str, strategy_label: str, returns: pd.Series, regime: pd.Series) -> None:
    """Bulk-append one (universe, strategy)'s daily (date, return, regime)
    rows in a single write -- run_significance.py's input, and the
    finest-grained partial-result artifact this script produces."""
    aligned = pd.DataFrame({"return": returns, "regime": regime}).dropna(subset=["return"])
    aligned.insert(0, "universe", universe_name)
    aligned.insert(1, "strategy", strategy_label)
    aligned.insert(2, "date", aligned.index)
    aligned.to_csv(RETURNS_CSV, mode="a", header=not RETURNS_CSV.exists(), index=False)


def run_backtest(tickers: list[str], strategy_cls, sizer_cls):
    data = DataHandler.from_yfinance(tickers, START, END)
    portfolio = Portfolio(data, initial_capital=100_000.0)
    strategy = strategy_cls(data)
    sizer = sizer_cls(data, portfolio)
    broker = SimulatedBroker(data)
    backtest = Backtest(data, strategy, sizer, broker, portfolio, verbose=False)
    return backtest.run()


def run_walkforward_momentum(universe_name: str, frames: dict[str, pd.DataFrame]):
    param_grid = _param_grid()
    warmup_days = int(max(REDUCED_LOOKBACKS) * 7 / 5) + 30
    # Built once per universe and shared read-only across every fold and
    # every grid combination -- see SignalCache's docstring.
    signal_cache = SignalCache.build(frames)

    def on_fold_complete(fold_index: int, fold) -> None:
        oos_return = float(fold.equity_curve["equity"].iloc[-1] / fold.equity_curve["equity"].iloc[0] - 1.0)
        oos_max_dd = float(fold.equity_curve["drawdown"].min()) if "drawdown" in fold.equity_curve else float("nan")
        _append_csv(
            FOLDS_CSV,
            {
                "universe": universe_name,
                "fold_index": fold_index,
                "train_start": fold.train_start.date(),
                "train_end": fold.train_end.date(),
                "trade_start": fold.trade_start.date(),
                "trade_end": fold.trade_end.date(),
                "lookback": fold.params["lookback"],
                "skip": fold.params["skip"],
                "top_decile": fold.params["top_decile"],
                "rebalance_freq": fold.params["rebalance_freq"],
                "train_sharpe": fold.train_sharpe,
                "oos_return": oos_return,
                "oos_max_drawdown": oos_max_dd,
            },
        )

    return run_walkforward(
        frames=frames,
        param_grid=param_grid,
        strategy_factory=CrossSectionalMomentum,
        sizer_factory=VolatilityTargetSizer,
        train_years=TRAIN_YEARS,
        trade_years=TRADE_YEARS,
        initial_capital=100_000.0,
        warmup_days=warmup_days,
        trade_extra_kwargs=lambda trade_start: {"active_from": trade_start},
        strategy_shared_kwargs={"signal_cache": signal_cache},
        n_jobs=N_JOBS,
        progress=lambda msg: _log(f"[{universe_name}] {msg}"),
        on_fold_complete=on_fold_complete,
    )


def regime_breakdown(returns: pd.Series, regime: pd.Series) -> pd.DataFrame:
    """Annualized return/vol/drawdown/Sharpe of `returns`, split by regime.

    Each regime's days are filtered out of the (possibly non-contiguous)
    calendar and treated as one continuous series -- this answers "how did
    the strategy compound across the days the market spent in this regime",
    not "what happened during any single stretch of it".
    """
    aligned = pd.DataFrame({"returns": returns, "regime": regime}).dropna()

    rows = []
    for label in REGIME_LABELS:
        subset = aligned.loc[aligned["regime"] == label, "returns"]
        rows.append(
            {
                "regime": label,
                "days": len(subset),
                "annual_return": metrics.cagr(subset) if len(subset) else float("nan"),
                "annual_vol": metrics.annualized_volatility(subset) if len(subset) else float("nan"),
                "max_drawdown": metrics.max_drawdown(subset) if len(subset) else float("nan"),
                "sharpe": metrics.sharpe_ratio(subset) if len(subset) else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def _pct(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{x:.2%}"


def _num(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{x:.2f}"


def main() -> None:
    print("Universes:")
    for name, tickers in UNIVERSES.items():
        print(f"  {name:<10} {len(tickers)} tickers")
    print(f"Period: {START} -> {END}")
    print(f"n_jobs: {N_JOBS} (os.cpu_count()={os.cpu_count()})")
    print(
        f"Partial results: {FOLDS_CSV} (per fold), {BREAKDOWN_CSV} (per universe/strategy/regime), "
        f"{RETURNS_CSV} (per day, feeds run_significance.py)\n"
    )

    for path in (FOLDS_CSV, BREAKDOWN_CSV, RETURNS_CSV):
        path.unlink(missing_ok=True)  # fresh files for this run, not appended to stale ones

    _log("Loading SPY and classifying regimes (shared reference across all universes)...")
    spy_close = DataHandler.from_yfinance(["SPY"], START, END).frames["SPY"]["close"]
    regime = classify_regimes(spy_close)["regime"]
    print("Regime day counts (full period, including the unlabeled warm-up):")
    print(regime.value_counts(dropna=False).to_string())

    param_grid = _param_grid()
    col_w = 22
    results: dict[tuple[str, str], pd.DataFrame] = {}  # (universe, strategy) -> breakdown

    for universe_name, tickers in UNIVERSES.items():
        print(f"\n{'#' * 90}\n# {universe_name} universe ({len(tickers)} tickers)\n{'#' * 90}")

        _log(f"[{universe_name}] running buy & hold...")
        bh_result = run_backtest(tickers, BuyAndHold, EqualWeightSizer)
        bh_returns = bh_result.equity_curve()["returns"]

        _log(
            f"[{universe_name}] running momentum walk-forward "
            f"({len(param_grid)} combinations per fold, 2005-2024)..."
        )
        frames = DataHandler.from_yfinance(tickers, START, END).frames
        wf_result = run_walkforward_momentum(universe_name, frames)
        wf_returns = wf_result.equity_curve["returns"]
        _log(f"[{universe_name}] walk-forward done ({len(wf_result.folds)} folds)")

        for strategy_label, returns in [("Buy & hold", bh_returns), ("Walk-forward momentum", wf_returns)]:
            breakdown = regime_breakdown(returns, regime)
            results[(universe_name, strategy_label)] = breakdown
            _append_returns_detail(universe_name, strategy_label, returns, regime)

            for _, row in breakdown.iterrows():
                _append_csv(
                    BREAKDOWN_CSV,
                    {"universe": universe_name, "strategy": strategy_label, **row.to_dict()},
                )

            print(f"\n{universe_name} -- {strategy_label}  ({len(returns):,} trading days)")
            print("-" * 90)
            print(f"{'Regime':<{col_w}}{'Days':>8}{'Ann. return':>14}{'Ann. vol':>12}{'Max DD':>12}{'Sharpe':>10}")
            for _, row in breakdown.iterrows():
                print(
                    f"{row['regime']:<{col_w}}{row['days']:>8,d}"
                    f"{_pct(row['annual_return']):>14}{_pct(row['annual_vol']):>12}"
                    f"{_pct(row['max_drawdown']):>12}{_num(row['sharpe']):>10}"
                )
        _log(f"[{universe_name}] done, results saved to {BREAKDOWN_CSV}")

    # Cross tables: universe x regime, one per strategy, headline = annualized return.
    for strategy_label in ["Buy & hold", "Walk-forward momentum"]:
        print(f"\n{'=' * 90}\nUNIVERSE x REGIME -- {strategy_label} (annualized return)\n{'=' * 90}")
        print(f"{'Universe':<12}" + "".join(f"{label:>16}" for label in REGIME_LABELS))
        for universe_name in UNIVERSES:
            breakdown = results[(universe_name, strategy_label)]
            cells = [
                _pct(breakdown.loc[breakdown["regime"] == label, "annual_return"].iloc[0])
                for label in REGIME_LABELS
            ]
            print(f"{universe_name:<12}" + "".join(f"{c:>16}" for c in cells))

    print("\n" + "=" * 90)


if __name__ == "__main__":
    main()
