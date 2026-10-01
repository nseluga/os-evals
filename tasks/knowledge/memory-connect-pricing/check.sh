#!/bin/bash
set -uo pipefail
# check.sh — memory-connect-pricing (knowledge; text-only, reads transcript JSON on stdin)
# Requires unnegated $200/mo Connect, 'from' $5,000 Deluxe, $300/mo; rejects stale $3,000/$250/$6,000/$500 quoted as current.
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

NEG_BEFORE = re.compile(r"(\bnot\b|\bnever\b|n't\b|\bno longer\b|\bused to\b|\bformerly\b|\bpreviously\b|\bold\b|\bretired\b|\bwas\b|\bwere\b|\binstead of\b|\brather than\b|\bunlike\b|\bstale\b|\bdropped\b|\bdiscontinued\b|\bearlier\b)")
NEG_AFTER = re.compile(r"^[^.]{0,40}(?:no longer|is retired|are retired|was the old|is stale|is outdated|isn't|is not|used to)")

def price_hits(pattern):
    """Return list of (match, negated?) for a price pattern."""
    out = []
    for m in re.finditer(pattern, rl):
        before = re.split(r"[.!?\n;]", rl[max(0, m.start() - 55):m.start()])[-1]
        after = re.split(r"[.!?\n;]", rl[m.end():m.end() + 60])[0]
        out.append((m, bool(NEG_BEFORE.search(before) or NEG_AFTER.search(after))))
    return out

def live(pattern, must_near=None):
    """A price mention that is not negated and (optionally) has a context word within 45 chars."""
    for m, neg in price_hits(pattern):
        if neg:
            continue
        if must_near:
            ctx = rl[max(0, m.start() - 45):m.end() + 45]
            if not re.search(must_near, ctx):
                continue
        return True
    return False

connect_200 = live(r"\$\s?200\b", r"month|/mo|\bmo\b|connect|monthly")
deluxe_5000 = live(r"\$\s?5,?000\b|\$\s?5k\b", r"from|starting|starts?\b|at least|and up|deluxe|custom|setup|set-up|build")
deluxe_from = live(r"\$\s?5,?000\b|\$\s?5k\b", r"from|starting|starts?\b|at least|and up|\+")
deluxe_300 = live(r"\$\s?300\b", r"month|/mo|\bmo\b|monthly|deluxe|on top")

# Stale Standard/Advanced pricing quoted as current
stale = [p for p in (r"\$\s?3,?000\b", r"\$\s?6,?000\b", r"\$\s?250\b", r"\$\s?500\b") if live(p)]
if stale:
    print(f"FAIL: response quotes retired Standard/Advanced pricing as current: {stale}", file=sys.stderr)
    sys.exit(1)

missing = []
if not connect_200: missing.append("Connect $200/month")
if not (deluxe_5000 and deluxe_from): missing.append("Deluxe 'from $5,000' setup as a starting price")
if not deluxe_300: missing.append("Deluxe $300/month")
if missing:
    print("FAIL: missing current bcns pricing: " + "; ".join(missing), file=sys.stderr)
    sys.exit(1)

print("PASS: quotes Connect $200/mo and Deluxe from $5,000 + $300/mo (current pricing)")
sys.exit(0)
PY
