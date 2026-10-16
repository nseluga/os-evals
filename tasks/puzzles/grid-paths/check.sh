#!/bin/bash
set -uo pipefail
# check.sh — puzzles/grid-paths (text-only, reads transcript JSON on stdin). Seed 7 answer: 237.
# Exit: 0=PASS, 1=FAIL, 2=infra.
python3 -c '
import sys, json, re
EXPECTED = 237
try:
    result = json.load(sys.stdin).get("result") or ""
except Exception as e:
    print(f"FAIL: could not parse transcript JSON: {e}", file=sys.stderr); sys.exit(2)
t = result.replace("*", "").replace("`", "")
m = re.findall(r"answer\W{0,6}(-?\d[\d,]*)", t, re.I) or re.findall(r"-?\d[\d,]*", t)
if not m:
    print("FAIL: no integer in reply", file=sys.stderr); sys.exit(1)
got = int(m[-1].replace(",", ""))
if got != EXPECTED:
    print(f"FAIL: got {got}, expected {EXPECTED}", file=sys.stderr); sys.exit(1)
print(f"PASS: {got}")
'
