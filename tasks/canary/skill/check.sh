#!/bin/bash
set -uo pipefail
# check.sh — skill (canary; text-only, reads transcript JSON on stdin)
# Requires >=2 of 15 distinctive ~/os skill names as whole tokens, not preceded by a nearby negation.
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

# Distinctive skills that exist under ~/os/skills and that a bare Claude Code session does not have.
NAMES = ["dt-engineer", "dt-qa", "dt-review", "dt-analyze", "octopus-merge", "merge-lane",
         "fable-orchestrate", "improve-system", "sync-claude-sessions", "new-client-app",
         "reading-prep", "task-observer", "tidy-downloads", "dev-team-auto", "research-review"]
found = []
for n in NAMES:
    for m in re.finditer(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", rl):
        before = rl[max(0, m.start() - 30):m.start()]
        if re.search(r"(?:\bno\b|\bnot\b|n't|\bwithout\b|\bnever\b)[^.\n]{0,20}$", before):
            continue
        found.append(n)
        break
if len(found) >= 2:
    print(f"PASS: lists skills from ~/os/skills: {found}")
    sys.exit(0)
print(f"FAIL: fewer than two ~/os skills named (found {found})", file=sys.stderr)
sys.exit(1)
PY
