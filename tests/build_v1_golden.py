"""One-off: write tests/fixtures/v1_golden.csv from the CURRENT engine.

Only meaningful when run on the pre-v2 engine (commit 1b2ba42); kept for
provenance. Re-running it on later code would just re-bless that code.
"""

from pathlib import Path

from tests.golden_scenarios import run_scenarios, to_long

if __name__ == "__main__":
    out = Path(__file__).parent / "fixtures" / "v1_golden.csv"
    to_long(run_scenarios()).to_csv(out, index=False, float_format="%.17g")
    print(f"wrote {out}")
