#!/bin/bash
set -uo pipefail

# check.sh — pir-workload-feature (coding, knowledge-informed / contaminated)
#
# Property-based unit test for the ACWR feature. Deliberately convention-AGNOSTIC:
# it asserts domain-correct BEHAVIOR (ratio direction, current-game exclusion, finite
# output) — NOT Nate's idiosyncratic 28÷4 weekly normalization or rounding — so it does
# not reward reproducing an arbitrary repo constant. See CONTRACT-NOTE.md audit.
#
# Requires WORKSPACE_DIR (restored PIR base) with a pandas/numpy Python env.
# Drains transcript on stdin.

cat >/dev/null  # drain transcript

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "FAIL: WORKSPACE_DIR not set or not a directory (harness contract extension required)" >&2
    exit 2
fi

# Prefer the venv setup.sh provisioned in the restored workspace.
if [ -x "$WS/.venv/bin/python" ]; then
    PY="$WS/.venv/bin/python"
else
    PY="${PYTHON_BIN:-python3}"
fi

WS="$WS" "$PY" - <<'PY'
import os, sys
sys.path.insert(0, os.environ["WS"])
try:
    import pandas as pd
    import numpy as np
except Exception as e:
    print(f"FAIL: pandas/numpy not available in workspace env: {e}", file=sys.stderr); sys.exit(2)

try:
    from src.features.workload_features import build_workload_features
except Exception as e:
    print(f"FAIL: cannot import build_workload_features: {e}", file=sys.stderr); sys.exit(1)

def games(pitcher, rows):
    return pd.DataFrame(
        [{"pitcher": pitcher, "game_date": d, "pitch_count": p} for d, p in rows]
    )

def run(df):
    out = build_workload_features(df.copy())
    assert "acwr_7_28" in out.columns, "output missing acwr_7_28 column"
    return out

def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr); sys.exit(1)

# --- Property 1: column exists, all values finite (safe division) ---
steady = games("A", [(f"2023-04-{d:02d}", 100) for d in range(1, 28, 2)])  # every 2 days
try:
    out = run(steady)
except AssertionError as e:
    fail(str(e))
except Exception as e:
    fail(f"build_workload_features raised on steady input: {e}")
vals = out["acwr_7_28"].to_numpy(dtype="float64")
if not np.all(np.isfinite(vals)):
    fail("acwr_7_28 contains inf/NaN — division not clamped safely")

# --- Property 2: current-game exclusion (no leakage) ---
# A pitcher whose FIRST-EVER appearance is huge. If the current game is (wrongly)
# counted in its own acute window, its acwr will be large. Correct impl: acute over
# PRIOR window is ~0, so the first row's acwr is small.
firstbig = games("B", [("2023-05-01", 500), ("2023-05-08", 50)])
outb = run(firstbig).sort_values("game_date").reset_index(drop=True)
first_acwr = float(outb.loc[0, "acwr_7_28"])
if first_acwr > 0.5:
    fail(f"first appearance acwr={first_acwr} too high — current game likely leaking "
         f"into its own acute window (should exclude current appearance)")

# --- Property 3: direction / monotonicity in acute load ---
# Two pitchers, identical long chronic baseline; on the final test game, HI has heavy
# recent (acute) load, LO has light recent load. HI's acwr must exceed LO's.
base = [(f"2023-03-{d:02d}", 40) for d in range(1, 29, 2)]  # steady chronic baseline
hi = games("C", base + [("2023-03-30", 120), ("2023-03-31", 120), ("2023-04-01", 40)])
lo = games("D", base + [("2023-03-30", 10),  ("2023-03-31", 10),  ("2023-04-01", 40)])
hi_last = float(run(hi).sort_values("game_date")["acwr_7_28"].iloc[-1])
lo_last = float(run(lo).sort_values("game_date")["acwr_7_28"].iloc[-1])
if not (hi_last > lo_last):
    fail(f"acwr not increasing in recent acute load (hi={hi_last} !> lo={lo_last}) — "
         f"ratio may be inverted or windows wrong")

print("PASS: acwr_7_28 is finite, excludes the current appearance, and rises with acute load")
sys.exit(0)
PY
rc=$?
if [ "$rc" -eq 0 ]; then
    echo "PASS: pir-workload-feature property tests passed"
fi
exit $rc
