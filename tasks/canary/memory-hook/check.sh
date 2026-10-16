#!/bin/bash
set -uo pipefail
# check.sh — memory-hook (canary; text-only, reads transcript JSON on stdin)
# Requires the project ref string.
# Exit: 0=PASS, 1=FAIL, 2=infra.

TRANSCRIPT="$(cat)"
TMPFILE="$(mktemp)"
echo "$TRANSCRIPT" > "$TMPFILE"

python3 - "$TMPFILE" <<'PY'
import sys, json, re

try:
    data = json.load(open(sys.argv[1]))
    result = data.get("result", "")
except Exception as e:
    print(f"FAIL: could not parse transcript JSON: {e}", file=sys.stderr)
    sys.exit(2)

rl = result.lower()

if re.search(r"cnsxbglhredokjbvudfd", rl):
    print("PASS: gave the project ref that only the memory file body contains")
    sys.exit(0)
print("FAIL: project ref not given", file=sys.stderr)
sys.exit(1)
PY
