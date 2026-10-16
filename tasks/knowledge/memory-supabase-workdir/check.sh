#!/bin/bash
set -uo pipefail
# check.sh — memory-supabase-workdir (knowledge; text-only, reads transcript JSON on stdin)
# Requires an unnegated `--workdir platform`; fails on any unnegated `migration repair` (prefix/suffix negation windows).
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

NEG_BEFORE = re.compile(r"(\bnot\b|\bnever\b|n't\b|\bavoid\b|\bwithout\b|\binstead of\b|\brather than\b|\bskip\b|\bno need\b|\bdon't\b|\bnor\b|\bdo not\b|\bhold off\b|\bstop\b|\bwarn)")
NEG_AFTER = re.compile(r"^.{0,70}?(?:is destructive|is dangerous|is risky|is unsafe|is a bad idea|would mark|will mark|marks? (?:the )?(?:applied|remote)|would revert|would be wrong|is the wrong|isn't the fix|is not the fix|is not what|isn't what)")

SENT = r"[.!?\n;]"

def hits(pattern, use_after):
    res = []
    for m in re.finditer(pattern, rl):
        before = re.split(SENT, rl[max(0, m.start() - 70):m.start()])[-1]     # same sentence only
        after = re.split(SENT, rl[m.end():m.end() + 90])[0]
        neg = bool(NEG_BEFORE.search(before)) or bool(NEG_AFTER.search(after)) if use_after else \
              bool(NEG_BEFORE.search(before)) or bool(re.search(r"(?:isn't|is not|not) (?:needed|necessary|required)|unnecessary", after))
        res.append(neg)
    return res     # list of "negated?" flags

repair = hits(r"migration repair", True)
workdir = hits(r"--workdir[= ]+[`'\"]?platform|workdir[`'\"]? (?:of |to |as |set to |=)?[`'\"]?platform", False)

if any(not n for n in repair):
    print("FAIL: response recommends running supabase migration repair", file=sys.stderr)
    sys.exit(1)
if not any(not n for n in workdir):
    print("FAIL: response does not recommend --workdir platform (or negates it)", file=sys.stderr)
    sys.exit(1)

print("PASS: recommends --workdir platform and does not recommend migration repair")
sys.exit(0)
PY
