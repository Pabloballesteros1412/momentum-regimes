# Volatility-scaled momentum and momentum crashes (HYPOTHESES.md H6)

**Short answer.** A long-only version of Barroso & Santa-Clara's scaling
cuts crash-window drawdowns on the fixed 37-name US universe, but it
doesn't improve risk-adjusted return anywhere. On the point-in-time
S&P 500 it **lowers** Sharpe, significantly, and its crash protection is
negligible.

| | US fixed 37 names | PIT S&P 500 (renamed) |
|---|---|---|
| **H6a** (shallower drawdown in both crash windows) | **Pass**, by a wide margin in 2009 | **Pass, technically**, by 0.3 and 0.04 points |
| **H6b** (Sharpe, scaled − baseline) | −0.03, CI [−0.20, +0.11], n.s. | **−0.09, CI [−0.18, −0.007], significant, wrong direction** |

## Design

- **Strategy:** `quantbt/strategies/volscaled.py`, with
  `test_volscaled.py`. Momentum's selection is unchanged. The book's
  gross exposure is min(target / σ̂, 1), where σ̂ is the 126-day realised
  volatility of an equal-weight portfolio of the selected names, from
  past closes only. The rest is cash, with no leverage.
- **Book-level scaling:** the scale goes to the whole book through
  `GrossTargetSizer`. Scaling each name separately would be undone by
  engine v2's cash cap, because vol-target weights usually sum past 100%.
- **Baseline:** the same machinery with target 10.0, so the scale is
  always 1 and the book is fully invested. That makes the comparison
  like-for-like.
- **Walk-forward:** the 12-combination grid over 2005–2024, with the same
  folds and warm-up as the regime study. Targets are fixed: 0.20 primary,
  with 0.15 and 0.25 as sensitivities.

## Results (`summary.csv`, `verdict.json`)

| Series | CAGR | Sharpe | Max DD | Worst month | Skew | Mean invested | 2009 rebound return | 2009 max DD | COVID return | COVID max DD |
|---|---|---|---|---|---|---|---|---|---|---|
| US baseline | 25.5% | 1.05 | −30.9% | −15.1% | −0.30 | 0.97 | +7.1% | −18.3% | +4.0% | −30.2% |
| US scaled 15% | 15.5% | 1.00 | −24.2% | −10.6% | −0.32 | 0.64 | +3.7% | −3.3% | −6.7% | −19.7% |
| **US scaled 20%** | 19.8% | 1.01 | −29.0% | −14.2% | −0.34 | 0.80 | +4.9% | **−4.3%** | −8.8% | **−25.5%** |
| US scaled 25% | 21.7% | 0.99 | −30.9% | −15.1% | −0.34 | 0.90 | +3.8% | −7.0% | −9.7% | −30.2% |
| US plain v2 (reference) | 27.2% | 1.06 | −35.9% | −15.8% | −0.24 | 0.99 | +11.2% | −8.2% | +5.5% | −35.0% |
| PIT baseline | 14.0% | 0.78 | −34.6% | −13.3% | −0.50 | 0.96 | +18.7% | −4.0% | −12.6% | −34.3% |
| **PIT scaled 20%** | 11.2% | 0.69 | −34.6% | −13.3% | −0.61 | 0.88 | **+3.5%** | −3.7% | −20.3% | −34.3% |
| PIT plain v2 (reference) | 14.0% | 0.72 | −35.3% | −13.2% | −0.46 | 0.98 | +11.9% | −4.8% | −11.9% | −34.7% |

Crash windows: 2009 rebound 2009-03-09 → 2009-06-30; COVID 2020-02-19 →
2020-06-30.

## Reading it

- **The mechanism works as designed, but it de-risks *after* the
  damage.** Realised volatility peaks right after a crash, so the scaled
  book is smallest exactly when the rebound comes. In COVID, the US
  scaled book's drawdown was shallower (−25.5% against −30.2%), but its
  window return was worse (−8.8% against +4.0%). In the 2009 rebound the
  PIT book made +3.5% against +18.7%.
- **A long-only book doesn't benefit the way the long-short factor
  does.** Barroso & Santa-Clara's gain comes from scaling down the
  *short* leg's crash risk in rebounds, when losers rally. A long-only
  winners book has no short leg. Its crash risk is mostly market risk,
  and scaling market risk by trailing volatility is a timing bet that
  didn't pay over 2009–2024.
- **On the broad PIT universe it costs Sharpe significantly** (−0.09),
  and CAGR falls from 14.0% to 11.2%.
- **On 37 names it reduces drawdowns with roughly unchanged Sharpe.**
  Lower risk for lower return, not a free lunch.

## Caveats

- The PIT H6a "pass" meets the pre-registered rule, but the margins are
  0.3 and 0.04 points. Reported as such, not as evidence of protection.
- Only one volatility estimator and window (126 days, equal-weight proxy)
  was tested, with no leverage. Barroso & Santa-Clara lever the factor up
  when its volatility is low. That isn't possible in this engine, and it
  is a large part of their result.

Reproduce: `python run_volscaled.py us pit analyze`.
