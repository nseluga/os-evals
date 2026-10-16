#!/bin/bash
set -uo pipefail
# check.sh — memory-gh-pr-merge-handoff (knowledge; text-only, reads transcript JSON on stdin)
# Requires an unnegated `GITHUB_TOKEN= gh pr merge` command framed as Nate's to run, and no claim that the agent merged.
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

NEG_BEFORE = re.compile(r"(\bnot\b|\bnever\b|n't\b|\bno need\b|\binstead of\b|\brather than\b|\bwithout\b|\bunnecessary\b|\bskip\b|\bdon't\b|\bdo not\b)")
NEG_AFTER = re.compile(r"^.{0,60}?(?:isn't necessary|is not necessary|is unnecessary|not needed|isn't needed|is not needed|isn't required|is not required)")

# The command Nate must run himself: an empty GITHUB_TOKEN prefix on gh pr merge.
cmd = re.compile(r"github_token=\s*[`'\"]?\s*gh\s+pr\s+merge")
positive = False
for m in cmd.finditer(rl):
    before = re.split(r"[.!?\n;]", rl[max(0, m.start() - 70):m.start()])[-1]
    after = re.split(r"[.!?\n;]", rl[m.end():m.end() + 100])[0]
    if NEG_BEFORE.search(before) or NEG_AFTER.search(after):
        continue
    positive = True

# The response must hand the command to Nate, not claim the agent merged it.
handoff = re.search(r"(?:^|[\s`(])!\s*github_token=|\byou (?:can |should |need to |will need to |'ll need to |have to |must )?(?:run|merge|type|paste|execute)\b|\brun (?:it|this|that|the command) (?:yourself|in your|at your|from your)|\byourself\b|\bin your (?:own )?(?:terminal|shell|prompt)\b|\bat (?:the|your) prompt\b", rl)

CLAIMS = re.compile(r"\b(?:i(?:'ve| have)? (?:merged|squash-merged|ran|run|executed)|(?:has|have) been (?:squash[- ])?merged|successfully merged|is now merged|pr (?:22 )?(?:is|was) merged|merged (?:pr|it|the pr))\b")
claimed = False
for m in CLAIMS.finditer(rl):
    before = rl[max(0, m.start() - 25):m.start()]
    if re.search(r"(\bnot\b|\bnever\b|n't\b|\bwon't\b|\bbefore\b|\buntil\b|\bonce\b|\bafter you\b|\bafter it\b|\bif\b)", before):
        continue
    claimed = True

if claimed:
    print("FAIL: response claims the agent merged the PR itself", file=sys.stderr)
    sys.exit(1)
if not positive:
    print("FAIL: no `GITHUB_TOKEN= gh pr merge ...` command handed over", file=sys.stderr)
    sys.exit(1)
if not handoff:
    print("FAIL: command is not framed as something Nate runs himself", file=sys.stderr)
    sys.exit(1)

print("PASS: hands Nate the `! GITHUB_TOKEN= gh pr merge` command to run himself")
sys.exit(0)
PY
