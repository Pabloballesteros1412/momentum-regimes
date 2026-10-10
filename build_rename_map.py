"""Evidence-based rename map for the point-in-time S&P 500 (HYPOTHESES.md H1).

A historical member ticker T with no Yahoo data is mapped to a current
ticker T' only if (H1 mapping rule, fixed before this script was run):

  1. Same legal entity on SEC EDGAR: the company (CIK) that currently trades
     as T' either
       B. lists T's company name (from Wikipedia's S&P 500 change table, or
          the hand-written HAND_NAMES below) as its current or a former name.
     (Check A -- the CIK changed its name within +-120 days of the swap --
     was in the pre-registered rule as an alternative to B. It was dropped
     after the first pass showed it accepts acquisitions where the acquirer
     renamed itself; it is still computed and reported.)
  2. Continuous prices: T''s Yahoo series has a bar on >= 99% of T's
     member-days, and starts on or before T's first member-day.
  3. No double counting: T's membership doesn't overlap T''s.

Candidates are adjacent swaps in the fja05680 membership: T's membership
ends and T''s begins within 3 trading days. That catches ticker changes that
the index itself records as a remove/add pair. One hop only; a chain
(T -> T' -> T'') is followed when T' itself has no prices.

Inputs: data/sp500_membership_intervals.csv, results/pit_us/coverage_by_ticker.csv,
cache/pit/ (Yahoo, from build_universe_us.py), a saved copy of Wikipedia's
"Historical components of the S&P 500" page (path as argv[1]), and SEC EDGAR
(company_tickers.json + submissions API; cached under argv[2]).

Outputs: data/sp500_rename_map.csv (accepted), results/pit_us_renamed/
rename_candidates.csv (every candidate with every check), and
data/sp500_membership_intervals_renamed.csv (intervals with T replaced by T').

    python build_rename_map.py <wikipedia_html> <edgar_cache_dir>
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

DATA = Path("data")
OUT = Path("results/pit_us_renamed")
CACHE = Path("cache/pit")
CALENDAR = Path("results/v2/spy_regime_rerun.csv")
# SEC requires a User-Agent with a contact address; a placeholder is used so
# no personal details are sent.
UA = "momentum-regimes-research research-bot@example.org"
ADJACENT_DAYS = 3
NAME_CHANGE_WINDOW = pd.Timedelta(days=120)
MIN_PRICE_COVERAGE = 0.99

# Old company names for tickers Wikipedia's change table doesn't name.
# Each is still verified against EDGAR (check B); a wrong guess just fails.
HAND_NAMES = {
    "ANTM": "Anthem", "PKI": "PerkinElmer", "BLL": "Ball Corp", "ABC": "AmerisourceBergen",
    "MYL": "Mylan", "SYMC": "Symantec", "GPS": "Gap", "CTL": "CenturyLink", "LB": "L Brands",
    "STI": "SunTrust", "UTX": "United Technologies", "CBS": "CBS Corp", "VIAC": "ViacomCBS",
    "FB": "Facebook", "COG": "Cabot Oil & Gas", "HFC": "HollyFrontier", "FISV": "Fiserv",
    "WLTW": "Willis Towers Watson", "CDAY": "Ceridian", "Q": "QuintilesIMS", "KFT": "Kraft Foods",
    "PCLN": "Priceline", "TMK": "Torchmark", "BBT": "BB&T", "ADS": "Alliance Data",
    "RE": "Everest Re", "FLT": "FleetCor", "PEAK": "Healthpeak", "HCP": "HCP Inc",
    "DISCA": "Discovery", "TWX": "Time Warner", "WFM": "Whole Foods", "COV": "Covidien",
    # Added after reviewing the first pass (see RENAME_MAP.md): these three
    # passed only check A because no old name was on file.
    "DWDP": "DowDuPont", "BHGE": "Baker Hughes a GE Co", "HRS": "Harris Corp", "NLOK": "NortonLifeLock",
}


def _norm(name: str) -> str:
    name = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    stop = {"inc", "corp", "corporation", "co", "company", "ltd", "plc", "the", "group", "holdings", "de", "new", "llc",
            "lp", "sa", "nv", "international", "intl"}
    return " ".join(w for w in name.split() if w not in stop)


def _names_match(old: str, edgar: str, strict: bool = True) -> bool:
    """Strict: every token of the old name appears in the EDGAR name and the
    first tokens agree; a single-token old name must match exactly. (A first
    pass used substring matching and accepted e.g. "IES Holdings" for
    "Life Technologies"; see RENAME_MAP.md.)"""
    a, b = _norm(old).split(), _norm(edgar).split()
    if not a or not b or a[0] != b[0]:
        return False
    if len(a) == 1 and strict:
        return a == b
    return set(a) <= set(b)


def _get(url: str, cache: Path) -> dict:
    if cache.exists():
        return json.loads(cache.read_text())
    time.sleep(0.15)  # SEC fair-access: well under 10 requests/second
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    cache.write_text(body)
    return json.loads(body)


def main() -> None:
    wiki_html, edgar_dir = Path(sys.argv[1]), Path(sys.argv[2])
    edgar_dir.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    days = pd.DatetimeIndex(pd.read_csv(CALENDAR, index_col=0, parse_dates=True).index).sort_values()
    pos = {d: i for i, d in enumerate(days)}
    iv = pd.read_csv(DATA / "sp500_membership_intervals.csv", parse_dates=["start", "end"])
    cov = pd.read_csv("results/pit_us/coverage_by_ticker.csv").set_index("ticker")
    missing = set(cov.index[cov["status"] == "missing"])

    wiki = pd.read_html(wiki_html)[0]
    wiki.columns = ["date", "add_t", "add_s", "rem_t", "rem_s", "reason", "refs"]
    wiki_names = {t: s for t, s in zip(wiki["rem_t"], wiki["rem_s"]) if isinstance(t, str) and isinstance(s, str)}

    tickers_json = _get("https://www.sec.gov/files/company_tickers.json", edgar_dir / "company_tickers.json")
    cik_of = {v["ticker"].upper().replace("-", "."): int(v["cik_str"]) for v in tickers_json.values()}

    def prices(t: str, fetch: bool = False):
        f = CACHE / f"{t}.parquet"
        if not f.exists() and fetch:
            import yfinance as yf
            raw = yf.download(t.replace(".", "-"), start="2005-01-01", end="2024-12-31", auto_adjust=True,
                              progress=False)
            if raw is not None and not raw.empty:
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = raw.columns.get_level_values(0)
                raw.columns = [str(c).lower() for c in raw.columns]
                df = raw[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
                df = df[(df["close"] > 0) & (df["open"] > 0)]
                if not df.empty:
                    df.index.name = "timestamp"
                    df.to_parquet(f)
        return pd.read_parquet(f).index if f.exists() else None

    member_days = {t: days[days.isin(pd.DatetimeIndex(
        [d for s, e in zip(g["start"], g["end"]) for d in days[(days >= s) & (days <= e)]]))]
        for t, g in iv.groupby("ticker")}

    starts = iv.groupby("start")["ticker"].apply(list)
    rows = []
    for _, r in iv[iv["ticker"].isin(missing)].iterrows():
        if r["end"] >= days[-1]:
            continue
        i = pos[r["end"]]
        for k in range(1, ADJACENT_DAYS + 1):
            if i + k >= len(days) or days[i + k] not in starts.index:
                continue
            for new in starts[days[i + k]]:
                if new == r["ticker"]:
                    continue
                rows.append({"old": r["ticker"], "old_end": r["end"], "new": new, "new_start": days[i + k]})
    cands = pd.DataFrame(rows).drop_duplicates(["old", "new"])

    def check(c, new) -> dict:
        old = c["old"]
        row = {"old": old, "old_end": pd.Timestamp(c["old_end"]).date(), "new": new,
               "new_start": None if pd.isna(c.get("new_start")) else pd.Timestamp(c["new_start"]).date(),
               "generator": c.get("generator", "adjacent"),
               "old_name": HAND_NAMES.get(old) or wiki_names.get(old), "old_name_source":
               "hand list" if old in HAND_NAMES else ("wikipedia" if old in wiki_names else None)}
        cik = cik_of.get(new)
        row["cik"] = cik
        if cik is None:
            row["decision"] = "reject: new ticker has no current EDGAR CIK"
            return row
        sub = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", edgar_dir / f"CIK{cik:010d}.json")
        former = sub.get("formerNames", []) or []
        row["edgar_name"] = sub.get("name")
        row["edgar_former_names"] = "; ".join(f"{f['name']} (to {str(f.get('to', ''))[:10]})" for f in former)
        swap = pd.Timestamp(c["old_end"])
        row["A_name_change_at_swap"] = any(
            f.get("to") and abs(pd.Timestamp(str(f["to"])[:10]) - swap) <= NAME_CHANGE_WINDOW for f in former)
        # Adjacent swaps carry structural evidence (the index itself swapped
        # T for T'), so a single-token old name may match as a prefix there
        # ("FleetCor" ~ "FLEETCOR TECHNOLOGIES"); name-search candidates have
        # no such evidence and need an exact single-token match.
        strict = row["generator"] == "name"
        row["B_old_name_on_cik"] = bool(row["old_name"]) and any(
            _names_match(row["old_name"], n, strict=strict) for n in [sub.get("name", "")] + [f["name"] for f in former])
        bars = prices(new, fetch=row["B_old_name_on_cik"])
        old_days = member_days[old]
        if bars is None:
            row["price_coverage"] = 0.0
        else:
            row["price_coverage"] = float(old_days.isin(bars).mean())
            row["first_bar"] = bars.min().date()
        row["C_prices_continuous"] = bars is not None and row["price_coverage"] >= MIN_PRICE_COVERAGE \
            and bars.min() <= old_days.min()
        row["D_no_overlap"] = not member_days[new].isin(old_days).any() if new in member_days else True
        # Check A alone proved unsafe (first pass, RENAME_MAP.md): an acquirer
        # that renames itself at the merger (BB&T -> Truist when it absorbed
        # SunTrust) changes its EDGAR name at the swap date too. B -- the old
        # company's own name on the same CIK -- is required; A is reported.
        ok_entity = row["B_old_name_on_cik"]
        if ok_entity and row["C_prices_continuous"] and row["D_no_overlap"]:
            row["decision"] = "ACCEPT"
        else:
            why = [w for w, ok in (("same entity (A/B)", ok_entity), ("price continuity", row["C_prices_continuous"]),
                                   ("no overlap", row["D_no_overlap"])) if not ok]
            row["decision"] = "reject: " + ", ".join(why)
        return row


    # Generator 2: the old company's name matches a current EDGAR company
    # title (renames that happened outside an index swap, e.g. after the
    # name left the index, or after 2024).
    titles = {}
    for v in tickers_json.values():
        titles.setdefault(_norm(v["title"]), []).append(v["ticker"].upper().replace("-", "."))
    extra = []
    for old in sorted(missing):
        name = HAND_NAMES.get(old) or wiki_names.get(old)
        if not name:
            continue
        for title, tks in titles.items():
            if _names_match(name, title):
                for new in tks:
                    if new != old and not ((cands["old"] == old) & (cands["new"] == new)).any():
                        end = iv.loc[iv["ticker"] == old, "end"].max()
                        extra.append({"old": old, "old_end": end, "new": new, "new_start": pd.NaT, "generator": "name"})
    cands = pd.concat([cands.assign(generator="adjacent"), pd.DataFrame(extra)], ignore_index=True)

    checked = []
    for _, c in cands.iterrows():
        checked.append(check(c, c["new"]))
    # Chains: old -> mid has no current CIK, but mid -> new was accepted.
    for _ in range(3):
        accepted = {r["old"]: r["new"] for r in checked if r["decision"] == "ACCEPT"}
        added = False
        for r in list(checked):
            if r["decision"].startswith("reject: new ticker has no current EDGAR CIK") and r["new"] in accepted \
                    and not any(x["old"] == r["old"] and x["new"] == accepted[r["new"]] for x in checked):
                c = pd.Series({"old": r["old"], "old_end": pd.Timestamp(r["old_end"]), "new_start": pd.NaT,
                               "generator": f"chain via {r['new']}"})
                checked.append(check(c, accepted[r["new"]]))
                added = True
        if not added:
            break

    out = pd.DataFrame(checked)

    out.to_csv(OUT / "rename_candidates.csv", index=False)
    acc = out[out["decision"] == "ACCEPT"]
    # One target per old ticker; more than one accepted target would be ambiguous.
    dup = acc["old"].duplicated(keep=False)
    if dup.any():
        print("ambiguous (dropped):", acc[dup][["old", "new"]].values.tolist())
        acc = acc[~dup]
    acc.to_csv(DATA / "sp500_rename_map.csv", index=False)
    mapping = dict(zip(acc["old"], acc["new"]))
    renamed = iv.assign(ticker=iv["ticker"].map(lambda t: mapping.get(t, t)))
    renamed.to_csv(DATA / "sp500_membership_intervals_renamed.csv", index=False, date_format="%Y-%m-%d")
    print(f"{len(cands)} candidate pairs for {cands['old'].nunique()} missing tickers; "
          f"{len(acc)} accepted")
    print(out["decision"].value_counts().to_string())


if __name__ == "__main__":
    main()
