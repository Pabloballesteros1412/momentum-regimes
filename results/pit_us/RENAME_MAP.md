# Rename map for the point-in-time S&P 500 (task 1, HYPOTHESES.md H1)

Twenty historical S&P 500 tickers with no Yahoo data were mapped to the
current ticker of **the same legal entity**. Each mapping has two pieces of
documented evidence:

- **EDGAR:** the SEC company record (CIK) that trades today under the new
  ticker lists the old company's name as its current or a former name.
- **Prices:** the new ticker's Yahoo series has a bar on 100% of the old
  ticker's 2005–2024 member-days, and starts on or before the first of
  them.

A third check confirms the old and new tickers are never members on the
same day. The script is `build_rename_map.py`. Every candidate and every
check is in `results/pit_us_renamed/rename_candidates.csv`, and the
accepted map is in `data/sp500_rename_map.csv`. The EDGAR responses were
fetched on 2026-10-11 with a placeholder contact address in the
User-Agent.

## Accepted mappings

| Old → new | Old name (source) | EDGAR CIK and current name | EDGAR former names (to date) | Prices | How found |
|---|---|---|---|---|---|
| ABC → COR | AmerisourceBergen (hand) | 1140859 Cencora, Inc. | AMERISOURCEBERGEN CORP (2023-08-15) | 100%, from 2005 | adjacent swap |
| ANTM → ELV | Anthem (hand) | 1156039 Elevance Health | Anthem, Inc. (2022-06-24); WELLPOINT (2014); ANTHEM INC (2004) | 100%, from 2005 | adjacent swap |
| BHGE → BKR | Baker Hughes a GE Co (hand) | 1701605 Baker Hughes Co | Baker Hughes a GE Co (2019-10-10) | 100%, from 2005 | adjacent swap |
| BLL → BALL | Ball Corp (hand) | 9389 BALL Corp | (ticker change only; current name matches) | 100%, from 2005 | adjacent swap |
| CTL → LUMN | CenturyLink (hand) | 18926 Lumen Technologies | CENTURYLINK, INC (2021-01-20); CENTURYTEL (2010) | 100%, from 2005 | adjacent swap |
| DWDP → DD | DowDuPont (hand) | 1666700 DuPont de Nemours | DowDuPont Inc. (2019-05-31) | 100%, from 2005 | adjacent swap |
| FB → META | Facebook (hand) | 1326801 Meta Platforms | Facebook Inc (2021-10-27) | 100%, from IPO 2012 | adjacent swap |
| FLT → CPAY | FleetCor (hand) | 1175454 Corpay, Inc. | FLEETCOR TECHNOLOGIES INC (2024-03-14) | 100%, from IPO 2010 | adjacent swap |
| HRS → LHX | Harris Corp (hand) | 202058 L3Harris Technologies | HARRIS CORP /DE/ (2019-06-25) | 100%, from 2005 | adjacent swap |
| LB → BBWI | L Brands (hand) | 701985 Bath & Body Works | L Brands, Inc. (2021-07-30); LIMITED BRANDS (2013) | 100%, from 2005 | adjacent swap |
| NLOK → GEN | NortonLifeLock (hand) | 849399 Gen Digital | NortonLifeLock Inc. (2022-10-12); SYMANTEC CORP (2019-10-24) | 100%, from 2005 | adjacent swap |
| PEAK → DOC | Healthpeak (hand) | 765880 Healthpeak Properties | HCP, INC. (2019-10-01) | 100%, from 2005 | adjacent swap |
| PKI → RVTY | PerkinElmer (hand) | 31791 Revvity, Inc. | PERKINELMER INC (2023-04-14) | 100%, from 2005 | adjacent swap |
| RE → EG | Everest Re (hand) | 1095073 Everest Group | EVEREST RE GROUP LTD (2023-07-06) | 100%, from 2005 | adjacent swap |
| TMK → GL | Torchmark (hand) | 320335 Globe Life | TORCHMARK CORP (2019-08-02) | 100%, from 2005 | adjacent swap |
| UTX → RTX | United Technologies (hand) | 101829 RTX Corp | UNITED TECHNOLOGIES CORP /DE/ (2020-04-06) | 100%, from 2005 | adjacent swap |
| WLTW → WTW | Willis Towers Watson (hand) | 1140536 Willis Towers Watson plc | (ticker change only; current name matches) | 100%, from 2005 | adjacent swap |
| GPS → GAP | Gap (hand) | 39911 GAP INC | (ticker change only; current name matches) | 100%, from 2005 | EDGAR name search |
| HCP → DOC | HCP Inc (hand) | 765880 Healthpeak Properties | HCP, INC. (2019-10-01) | 100%, from 2005 | chain via PEAK |
| SYMC → GEN | Symantec (hand) | 849399 Gen Digital | SYMANTEC CORP (2019-10-24) | 100%, from 2005 | chain via NLOK |

**Yahoo splices predecessor histories.** For example, BKR before 2017 is
the old Baker Hughes Inc., and DD before 2017 is the old E. I. du Pont.
The mapping covers only the old ticker's own member-days: BHGE 2017–2019,
DWDP 2017–2019. Those fall inside the same-entity period on EDGAR.
Earlier history is used only as momentum look-back.

## How the rule was tightened (deviations from the pre-registered rule)

Both changes were made after inspecting the candidate list and **before
the H1 test was run**. Both make the rule stricter.

1. **Check A dropped as sufficient.** Check A was "the CIK changed its name
   within ±120 days of the ticker swap". The first pass accepted it alone,
   and that let through acquisitions where the *acquirer* renamed itself
   at the merger:
   - SunTrust → Truist (BB&T's CIK);
   - CBS and Viacom → Truist / Old Dominion (unrelated renames in the same
     week);
   - Mylan → Viatris (Upjohn's CIK);
   - WestRock → Smurfit Westrock;
   - Allied Waste → Republic Services;
   - Cimarex → Trane;
   - Lexmark → Pentair.

   Check B, the old company's *own* name on the same CIK, is now required.
   Three true renames had passed only on A because no old name was on file
   (BHGE, HRS, NLOK). Their old names were added to the hand list, and
   they then passed B.
2. **Strict name matching.** A substring match accepted nonsense pairs
   such as "Life Technologies" → IES Holdings ("ies" is inside
   "technologies") and Twitter → ITT. The rule is now: every token of the
   old name appears in the EDGAR name, and the first tokens agree. A
   single-token old name needs an exact match for EDGAR name-search
   candidates. For adjacent index swaps it may match as a prefix
   ("FleetCor" ~ "FLEETCOR TECHNOLOGIES"), because the swap itself is
   structural evidence.

## Rejected candidates worth noting

| Candidate | Why rejected |
|---|---|
| ARNC → HWM (Arconic → Howmet) | Yahoo HWM starts 2016-11; covers 22% of ARNC member-days |
| DISCA / DISCK → WBD | WBD has no prices before 2022 on Yahoo; 0% coverage |
| BRCM → AVGO | Different entity (Avago acquired Broadcom Corp); also overlap |
| MYL → VTRS | Viatris is Upjohn's CIK, not Mylan's |
| STI → TFC | Truist is BB&T's CIK, not SunTrust's |
| 154 candidates | The new ticker has no current EDGAR CIK (itself delisted) |

## Effect

See `results/pit_us_renamed/FINDINGS_RENAMED.md`.
