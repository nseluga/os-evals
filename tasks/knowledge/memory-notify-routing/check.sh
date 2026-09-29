#!/bin/bash
set -uo pipefail
# check.sh — memory-notify-routing (knowledge; text-only, reads transcript JSON on stdin)
# Requires reply->Brandon (Nate not a recipient) and signed->Nate; negation-aware per clause.
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

NEG = re.compile(r"(\bnot\b|\bnever\b|\bno\b|n't\b|\bwithout\b|\bexcept\b|\binstead of\b|\brather than\b|\bexcluding\b|\bskip\b|\bleave (?:nate|brandon) out\b)")
NEG_AFTER = re.compile(r"^\W*(?:does not|doesn't|is not|isn't|never|won't|will not|stays out|need not|needn't|shouldn't|should not|is left out|is not emailed|doesn't get)")

# split into clauses: sentences, lines, table rows, semicolons, contrast conjunctions
clauses = [c.strip() for c in re.split(r"[.!?\n;]+|,\s*(?:and|but|while)\b|\bwhile\b|\bwhereas\b|\bbut\b", rl.replace("|", " ")) if c.strip()]

REPLY = re.compile(r"\brepl(?:y|ies|ied|ying)\b|\bresponds?\b|\bresponded\b|\bwants? a call\b|\bneeds? a call\b|\bstopped replying\b")
SIGN = re.compile(r"\bsign(?:s|ed|ing)?\b|\bonboard(?:ing)?\b|\bcloses?\b|\bclosed\b|\bconvert(?:s|ed)?\b")

def mentions_positive(clause, who):
    """True if `who` appears in the clause and is not negated at that spot."""
    for m in re.finditer(who, clause):
        before = clause[max(0, m.start() - 45):m.start()]
        after = clause[m.end():m.end() + 30]
        if NEG.search(before) or NEG_AFTER.search(after):
            continue
        return True
    return False

# Nate may be addressed as "you" (the prompt says "me (Nate)"): count "you" only in recipient-like positions.
NATE = (r"\bnate\b|\bme\b|\bto you\b|\b(?:email|notify|cc|copy|tell|ping) you\b"
        r"|\byou(?= (?:and|&|both|should|would|will|also|get|receive|are|be)\b)")

reply_brandon = reply_nate = sign_nate = sign_brandon = False
for c in clauses:
    r, s = bool(REPLY.search(c)), bool(SIGN.search(c))
    if r == s:      # neither, or ambiguous clause covering both events: not evidence
        continue
    if r:
        reply_brandon |= mentions_positive(c, r"brandon")
        reply_nate |= mentions_positive(c, NATE)
    else:
        sign_nate |= mentions_positive(c, NATE)
        sign_brandon |= mentions_positive(c, r"brandon")

if not reply_brandon:
    print("FAIL: response does not route the lead-replied notification to Brandon", file=sys.stderr)
    sys.exit(1)
if reply_nate:
    print("FAIL: response also sends the lead-replied notification to Nate (rule: Brandon only)", file=sys.stderr)
    sys.exit(1)
if not sign_nate:
    print("FAIL: response does not send the lead-signed notification to Nate", file=sys.stderr)
    sys.exit(1)

print("PASS: replied -> Brandon only, signed -> Nate")
sys.exit(0)
PY
