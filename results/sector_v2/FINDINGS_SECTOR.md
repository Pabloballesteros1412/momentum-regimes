# Sector attribution under engine v2 (HYPOTHESES.md H3)

**Verdict (pre-registered rule): the composition story "partly holds"
under v2.** Three of the four published orderings hold. US momentum
carries consumer cyclicals and technology on more bearish rebalances than
Europe, and Europe carries healthcare more often than the US. The energy
ordering ("Europe more often than the US") fails. The concentration claim
also fails: under v2, Europe picks the concentrated 10% fraction *less*
often than the US.

There is also a finding about the published numbers. The published v1
shares counted the names momentum **selected**, not the names it actually
**held**. Under engine v1 those differ a lot, because selected names that
came later in the alphabet were often never bought (the cash bug). For
example, US healthcare was selected on 54.5% of bearish rebalances, the
published figure, but held on only 30.3%.

## Method

- Each walk-forward is replayed from its stored folds
  (`quantbt/validation/replay.py`). **All six replays (3 universes ×
  v1/v2) reproduce the stored out-of-sample equity to a relative ~3e-16**
  (`replay_check.csv`), so the holdings are the ones behind the published
  and v2 curves.
- Sectors come from Yahoo Finance's `sector` field, a snapshot taken on
  2026-10-11 (`data/sectors_yahoo.csv`). The published analysis's sector
  source wasn't in the repo.
- Bearish rebalances are monthly rebalance days with a bearish SPY trend
  label. There are **33** of them in 2009–2024, the same count as the
  README.
- `share_holding` is the share of those rebalances whose settled portfolio
  holds at least one name in the sector. `share_selected` is the same for
  the names selected that day. `mean_value_weight` is the sector's average
  share of portfolio value.

### Method check against the published v1 numbers (`method_check_v1.csv`)

| | Published v1 | Replay v1, selected | Replay v1, held |
|---|---|---|---|
| US consumer cyclical | 72.7% | **72.7%** | 66.7% |
| US technology | 57.6% | **57.6%** | 54.5% |
| US healthcare | 54.5% | **54.5%** | 30.3% |
| US energy | 27.3% | **27.3%** | 27.3% |
| Europe consumer cyclical | 30.3% | 27.3% | 18.2% |
| Europe technology | 18.2% | **18.2%** | 15.2% |
| Europe healthcare | 81.8% | **81.8%** | 81.8% |
| Europe energy | 42.4% | **42.4%** | 24.2% |

The selection-based replay reproduces 7 of the 8 published numbers
exactly. Europe consumer cyclical is off by one rebalance in 33, probably
because a name's Yahoo sector has been reclassified since publication.
So the published method is identified: it counted selections.

## v2 results, bearish rebalances (`sector_shares.csv`)

| Sector | US v1 held | US v2 held | Europe v1 held | Europe v2 held | US v2 weight | Europe v2 weight |
|---|---|---|---|---|---|---|
| Consumer cyclical | 66.7% | **81.8%** | 18.2% | **27.3%** | 17.8% | 5.4% |
| Technology | 54.5% | **72.7%** | 15.2% | **21.2%** | 24.3% | 3.5% |
| Healthcare | 30.3% | **57.6%** | 81.8% | **90.9%** | 16.6% | 37.1% |
| Energy | 27.3% | **42.4%** | 24.2% | **39.4%** | 13.0% | 17.1% |
| Consumer defensive | 33.3% | 51.5% | 24.2% | 75.8% | 10.4% | 17.3% |
| Communication services | 45.5% | 57.6% | 39.4% | 39.4% | 11.7% | 5.3% |

Under v2, selections and holdings nearly coincide. Exit cash is
redeployed, so selected names get bought.

| Ordering (H3) | v1 selected (published) | v1 held | v2 held |
|---|---|---|---|
| US > Europe, consumer cyclical | ✓ | ✓ | ✓ (81.8 vs 27.3) |
| US > Europe, technology | ✓ | ✓ | ✓ (72.7 vs 21.2) |
| Europe > US, healthcare | ✓ | ✓ | ✓ (90.9 vs 57.6) |
| Europe > US, energy | ✓ | ✗ | **✗ (39.4 vs 42.4)** |
| **Verdict** | holds (4/4) | partly (3/4) | **partly holds (3/4)** |

Energy is close either way. By value weight Europe still carries more
energy (17.1% vs 13.0%), but by the pre-registered share-holding metric
the US is slightly ahead.

### Concentration (`concentration.csv`)

| Share of folds choosing the 10% fraction | v1 | v2 |
|---|---|---|
| US | 50.0% | 37.5% |
| Europe | 62.5% | **31.25%** |
| Emerging | 87.5% | 50.0% |

The README's "Europe is more concentrated" argument doesn't survive v2.

## Reading it

- **The sector tilt is real and survives the fix.** In bear markets, US
  momentum leans into tech and consumer cyclicals, while European momentum
  leans into healthcare and consumer staples. The v2 value weights make
  the contrast sharper: healthcare is 37% of European momentum on bearish
  rebalances against 17% in the US, and tech is 24% in the US against 4% in
  Europe.
- **But it no longer has a result to explain.** Under v2 the US has no
  significant bull/bear interaction (`results/v2`), while Europe still
  does. The published attribution tried to explain why the US *protects*
  and Europe doesn't. Read the other way, Europe's defensive tilt sits
  alongside momentum doing *worse* than buy & hold in European bear
  markets.
- **The concentration half of the README's explanation fails under v2.**
  Its sign reverses.

## Files

`run_sector_attribution.py`, `replay_check.csv`, `method_check_v1.csv`,
`sector_shares.csv` (all sectors, all three universes, bearish and all
rebalances, three metrics), `concentration.csv`, `verdict.json`.
