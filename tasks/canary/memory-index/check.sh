#!/bin/bash
set -uo pipefail
# check.sh — memory-index (canary; text-only, reads transcript JSON on stdin)
# Requires `bcns-leads` not immediately negated.
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

neg = re.search(r"(?:not|n't|no) [^.]{0,30}bcns-leads", rl)
if re.search(r"bcns-leads", rl) and not neg:
    print("PASS: named the GCP project from the MEMORY.md index line")
    sys.exit(0)
print("FAIL: GCP project `bcns-leads` not named", file=sys.stderr)
sys.exit(1)
PY
