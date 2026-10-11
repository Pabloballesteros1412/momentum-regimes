"""Point-in-time S&P 500 universe for the US survivorship check (PLAN.md item 1).

1. Membership: fja05680/sp500, "S&P 500 Historical Components & Changes
   (Updated).csv" (daily member lists since 1996). Pass the path of a local
   clone; the commit hash is recorded. Reduced to per-ticker membership
   intervals over 2005-2024 -> data/sp500_membership_intervals.csv.
2. Prices: every ticker that was a member at any point in 2005-2024 is
   requested from Yahoo Finance (the only free source reachable here; Stooq
   is blocked and Tiingo needs a key). Yahoo mostly drops delisted names and
   reuses symbols, so many will be missing. Cached under cache/pit/.
3. Coverage report -> results/pit_us/coverage*.csv: member-days with a
   price bar on that day, overall, by year, and the names never found.

Ticker reuse (a 2008 symbol pointing at a different company today) cannot
be fully detected without a second source. Two checks are applied and
reported: a Yahoo series that starts after the ticker's membership ended
covers none of its member-days, and one that starts more than 10 trading
days after its membership began is flagged as possible reuse.

    python build_universe_us.py /path/to/fja05680-sp500-clone
"""

from __future__ import annotations

import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

import pandas as pd

START, END = "2005-01-01", "2024-12-31"
MEMBERSHIP_FILE = "S&P 500 Historical Components & Changes (Updated).csv"
DATA = Path("data")
CACHE = Path("cache/pit")
OUT = Path("results/pit_us")
CHUNK = 40
# NYSE trading days (SPY's own calendar) -- membership counted on business
# days would charge every exchange holiday as a missing bar.
CALENDAR = Path("results/v2/spy_regime_rerun.csv")


@lru_cache(maxsize=1)
def trading_days() -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.read_csv(CALENDAR, index_col=0, parse_dates=True).index).sort_values()


def yahoo_symbol(ticker: str) -> str:
    return ticker.replace(".", "-")


def load_membership(repo: Path) -> pd.DataFrame:
    """Daily membership, 2005-2024: one row per (date, ticker)."""
    raw = pd.read_csv(repo / MEMBERSHIP_FILE, parse_dates=["date"])
    raw = raw.sort_values("date")
    # Each row is the member list from that date until the next row; carry
    # the list as of START forward too.
    first = raw[raw["date"] <= START].tail(1)
    raw = pd.concat([first, raw[(raw["date"] > START) & (raw["date"] <= END)]])
    days = trading_days()
    lists = raw.set_index("date")["tickers"].reindex(days.union(raw["date"])).ffill().reindex(days)
    rows = [(d, t) for d, s in lists.items() for t in s.split(",")]
    return pd.DataFrame(rows, columns=["date", "ticker"])


def intervals(daily: pd.DataFrame) -> pd.DataFrame:
    """(ticker, start, end) runs of consecutive trading-day membership."""
    out = []
    days = trading_days()
    pos = {d: i for i, d in enumerate(days)}
    for ticker, g in daily.groupby("ticker"):
        idx = sorted(pos[d] for d in g["date"])
        run_start = prev = idx[0]
        for i in idx[1:]:
            if i != prev + 1:
                out.append((ticker, days[run_start], days[prev]))
                run_start = i
            prev = i
        out.append((ticker, days[run_start], days[prev]))
    return pd.DataFrame(out, columns=["ticker", "start", "end"])


def download(tickers: list[str]) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    CACHE.mkdir(parents=True, exist_ok=True)
    missing_marker = CACHE / "_not_found.txt"
    not_found = set(missing_marker.read_text().split()) if missing_marker.exists() else set()
    frames = {}
    todo = []
    for t in tickers:
        f = CACHE / f"{t}.parquet"
        if f.exists():
            frames[t] = pd.read_parquet(f)
        elif t not in not_found:
            todo.append(t)
    for i in range(0, len(todo), CHUNK):
        chunk = todo[i:i + CHUNK]
        print(f"  downloading {i + 1}-{i + len(chunk)} of {len(todo)}", flush=True)
        raw = yf.download([yahoo_symbol(t) for t in chunk], start=START, end=END, auto_adjust=True,
                          progress=False, group_by="ticker", threads=True)
        for t in chunk:
            y = yahoo_symbol(t)
            try:
                df = raw[y] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                not_found.add(t)
                continue
            df = df.copy()
            df.columns = [str(c).lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
            df = df[(df["close"] > 0) & (df["open"] > 0)]
            if df.empty:
                not_found.add(t)
                continue
            df.index.name = "timestamp"
            df.to_parquet(CACHE / f"{t}.parquet")
            frames[t] = df
        missing_marker.write_text("\n".join(sorted(not_found)))
    # Batch downloads get throttled: retry every miss once, one at a time.
    retried = CACHE / "_retried.txt"
    done = set(retried.read_text().split()) if retried.exists() else set()
    for t in sorted(not_found - done):
        time.sleep(0.5)
        raw = yf.download(yahoo_symbol(t), start=START, end=END, auto_adjust=True, progress=False)
        done.add(t)
        if raw is None or raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw.columns = [str(c).lower() for c in raw.columns]
        df = raw[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
        df = df[(df["close"] > 0) & (df["open"] > 0)]
        if df.empty:
            continue
        df.index.name = "timestamp"
        df.to_parquet(CACHE / f"{t}.parquet")
        frames[t] = df
        not_found.discard(t)
        print(f"  retry found {t}", flush=True)
    missing_marker.write_text("\n".join(sorted(not_found)))
    retried.write_text("\n".join(sorted(done)))
    return frames


def main() -> None:
    repo = Path(sys.argv[1])
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    DATA.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    daily = load_membership(repo)
    iv = intervals(daily)
    iv.to_csv(DATA / "sp500_membership_intervals.csv", index=False, date_format="%Y-%m-%d")
    (DATA / "sp500_membership_SOURCE.txt").write_text(
        f"Source: https://github.com/fja05680/sp500, file '{MEMBERSHIP_FILE}'\n"
        f"Commit: {commit}\nDownloaded: 2026-10-10\nReduced to trading-day (SPY calendar) membership intervals, {START} to {END}.\n")
    tickers = sorted(iv["ticker"].unique())
    print(f"{len(tickers)} distinct tickers were S&P 500 members in {START[:4]}-{END[:4]} "
          f"({len(daily):,} member-days)")

    frames = download(tickers)

    rows = []
    covered_flags = {}
    for t in tickers:
        member_days = pd.DatetimeIndex(daily.loc[daily["ticker"] == t, "date"])
        df = frames.get(t)
        bars = df.index if df is not None else pd.DatetimeIndex([])
        hit = member_days.isin(bars)
        covered_flags[t] = pd.DataFrame({"date": member_days, "covered": hit})
        t_iv = iv[iv["ticker"] == t]
        first_bar = bars.min() if len(bars) else pd.NaT
        late_start = bool(len(bars)) and any(
            first_bar > s + pd.tseries.offsets.BDay(10) and first_bar <= e for s, e in zip(t_iv["start"], t_iv["end"]))
        rows.append({"ticker": t, "member_days": len(member_days), "covered_days": int(hit.sum()),
                     "first_member": member_days.min().date(), "last_member": member_days.max().date(),
                     "first_bar": first_bar.date() if len(bars) else None,
                     "last_bar": bars.max().date() if len(bars) else None,
                     "still_member_2024": bool(member_days.max() >= trading_days()[-1]),
                     "status": "found" if hit.all() else ("missing" if not hit.any() else "partial"),
                     "possible_ticker_reuse": late_start,
                     # Late start AND the name left the index: Yahoo's symbol now
                     # belongs to a later company (e.g. SII, KG). Excluded.
                     "excluded_reused_ticker": bool(late_start and member_days.max() < trading_days()[-1])})
    cov = pd.DataFrame(rows)
    excluded = cov.loc[cov["excluded_reused_ticker"], "ticker"].tolist()
    (DATA / "sp500_excluded_tickers.txt").write_text("\n".join(excluded) + "\n")
    for t in excluded:
        covered_flags[t]["covered"] = False
    cov.loc[cov["excluded_reused_ticker"], ["covered_days", "status"]] = [0, "excluded (reused ticker)"]
    cov.to_csv(OUT / "coverage_by_ticker.csv", index=False)
    flags = pd.concat(covered_flags.values())
    by_year = flags.groupby(flags["date"].dt.year)["covered"].agg(["size", "sum"])
    by_year.columns = ["member_days", "covered_days"]
    by_year["coverage"] = by_year["covered_days"] / by_year["member_days"]
    by_year.to_csv(OUT / "coverage_by_year.csv")
    summary = {
        "distinct_tickers": len(tickers),
        "found_fully": int((cov["status"] == "found").sum()),
        "found_partially": int((cov["status"] == "partial").sum()),
        "excluded_reused": int(cov["status"].str.startswith("excluded").sum()),
        "missing_entirely": int((cov["status"] == "missing").sum()),
        "missing_still_member_2024": int(((cov["status"] == "missing") & cov["still_member_2024"]).sum()),
        "possible_ticker_reuse": int(cov["possible_ticker_reuse"].sum()),
        "excluded_reused_ticker": int(cov["excluded_reused_ticker"].sum()),
        "member_days": int(flags["covered"].size),
        "member_days_covered": int(flags["covered"].sum()),
        "member_day_coverage": float(flags["covered"].mean()),
        "membership_commit": commit,
    }
    pd.Series(summary).to_csv(OUT / "coverage_summary.csv", header=["value"])
    print(pd.Series(summary).to_string())
    print(by_year.to_string())


if __name__ == "__main__":
    main()
