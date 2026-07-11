#!/bin/bash
set -uo pipefail

# check.sh — rangestats-engine (coding, clean)  [DRAFT — under tasks/_draft, auto-excluded]
#
# Gate: run the vendored correctness + performance + scalability battery
# (test_rangestats.py) against the src/rangestats package the model wrote in
# WORKSPACE_DIR. Pure stdlib python; no server, no network. Vendored so the model can't
# edit the test. A too-slow (O(N)-per-query) design is interrupted by SIGALRM and fails.
#
# Quality dimensions: PERFORMANCE (large interleaved workload under a time bound) +
# SCALABILITY (sub-quadratic growth at 4x size) + functional correctness/validation.
#
# rc: 0 = pass, 1 = real task failure, 2 = infra/unscoreable (WORKSPACE_DIR unset).

cat >/dev/null  # drain transcript on stdin (unused; this is a perf/unit check)

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "INFRA: WORKSPACE_DIR not set or not a directory" >&2
    exit 2
fi

CHECK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WORKSPACE_DIR="$WS" python3 "$CHECK_DIR/test_rangestats.py"
rc=$?
if [ "$rc" -eq 0 ]; then
    echo "PASS: rangestats correctness + performance + scalability battery passed"
fi
exit $rc
