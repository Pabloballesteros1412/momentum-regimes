# Momentum regime explorer (static prototype)

`index.html` is a single static page. It reads the JSON export in
`data/v2/`, written by `export_results.py` and checked by
`test_export.py`. You pick a universe, a strategy (momentum or short-term
reversal) and an SPY regime. The page then shows:

- the growth of $1 on a log scale, for the strategy and for equal-weight
  buy & hold, with the chosen regime's days shaded;
- the drawdown from the running peak;
- metrics against buy & hold, for the whole common window or for the
  chosen regime's days only.

It also gives a one-line summary of that universe's pre-registered
regime test.

No build step, no dependencies, no external requests. Serve the folder
over HTTP so the browser can fetch the JSON:

```bash
cd web && python -m http.server 8000   # then open http://localhost:8000
```

It uses plain SVG and DOM APIs, follows the light/dark system setting,
and works at phone width.
