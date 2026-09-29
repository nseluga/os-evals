#!/bin/bash
set -uo pipefail
# check.sh — claude-md (canary; text-only, reads transcript JSON on stdin)
# Requires `ls -L ~/.claude/skills/grill-me` (whitespace and backticks normalised).
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

norm = re.sub(r"\s+", " ", rl.replace("`", ""))
if re.search(r"ls\s+-l\s+~/\.claude/skills/grill-me", norm):
    print("PASS: gave the CLAUDE.md health-check command")
    sys.exit(0)
print("FAIL: health-check command `ls -L ~/.claude/skills/grill-me` not given", file=sys.stderr)
sys.exit(1)
PY
