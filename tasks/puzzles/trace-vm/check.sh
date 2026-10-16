#!/bin/bash
set -uo pipefail
# check.sh — puzzles/trace-vm (text-only, reads transcript JSON on stdin). Seed 7 key below.
# Exit: 0=PASS, 1=FAIL, 2=infra.
python3 -c '
import sys, json, re
EXPECTED = {"R0": 0, "R1": 841, "R2": 16, "depth": 1}
try:
    result = json.load(sys.stdin).get("result") or ""
except Exception as e:
    print(f"FAIL: could not parse transcript JSON: {e}", file=sys.stderr); sys.exit(2)
t = result.replace("*", "").replace("`", "")
got = {}
for k in EXPECTED:
    m = re.findall(r"\b" + k + r"\s*[=:]\s*(-?\d+)", t, re.I)
    if m: got[k] = int(m[-1])
if got != EXPECTED:
    print(f"FAIL: got {got}, expected {EXPECTED}", file=sys.stderr); sys.exit(1)
print(f"PASS: {got}")
'
