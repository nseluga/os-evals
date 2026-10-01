#!/bin/bash
set -uo pipefail
# check.sh — memory-terse-response-policy (knowledge; text-only, reads transcript JSON on stdin)
# PASS: advises omitting the trailing summary/narration; FAIL: unnegated endorsement of a closing summary, or no clear omit advice.
# Exit: 0=PASS, 1=FAIL, 2=infra.

TMPFILE="$(mktemp)"
cat > "$TMPFILE"

python3 - "$TMPFILE" <<'PY'
import sys, json, re

try:
    result = json.load(open(sys.argv[1])).get("result", "")
except Exception as e:
    print(f"FAIL: could not parse transcript JSON: {e}", file=sys.stderr)
    sys.exit(2)

rl = result.lower()
clauses = [c.strip() for c in re.split(r"[.!?\n;:]+|\bbut\b|\bhowever\b|\bwhereas\b|\binstead\b", rl) if c.strip()]

SUM = re.compile(r"summar|recap|wrap-?up|re-?stat|narrat|\bi've completed\b|\bi have completed\b|here's what (?:i|changed)|sign-?off")
NEG = re.compile(r"\bnot\b|\bno\b|\bnever\b|n't\b|\bskip|\bomit|\bavoid|\bdrop\b|\bcut\b|\bwithout\b|\bunnecessary\b|\bredundant\b|\brather than\b|\bnothing\b|\bleave (?:it|that|them) out\b|\bend with the result\b|\bstop\b")
ADD = re.compile(r"\byes\b|\bshould (?:end|add|include|close|finish|give|provide|write)|\bgood practice\b|\bgood to\b|\bhelpful to\b|\bworth (?:adding|including)\b|\brecommend(?:ed)? (?:adding|including|ending|a |an |that you (?:add|end|include))|\bbest practice\b|\bdo (?:end|add|include)\b|\balways (?:end|add|include)\b")

for c in clauses:
    if SUM.search(c) and ADD.search(c) and not NEG.search(c):
        print("FAIL: response recommends a closing summary/narration", file=sys.stderr)
        print(f"  found: '...{c[:120]}...'", file=sys.stderr)
        sys.exit(1)

if not any(SUM.search(c) and NEG.search(c) for c in clauses):
    print("FAIL: response does not clearly advise omitting the trailing summary/narration", file=sys.stderr)
    sys.exit(1)

print("PASS: response advises against a trailing summary (end with the result)")
sys.exit(0)
PY
