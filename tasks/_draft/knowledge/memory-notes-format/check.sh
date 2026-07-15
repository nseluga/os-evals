#!/bin/bash
set -uo pipefail
# check.sh — memory-notes-format (knowledge, rung-2/3 discriminating task)
#
# Validates that the response recommends one file per document (never a combined NOTES.md).
# Uses Python for context-aware checks to avoid false-positives on cautionary language
# ("never a combined notes file", "Invented structure before reading is noise").
#
# Drains transcript from stdin.
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

# --- Check 1: must recommend separate/dedicated file per document ---
ONEFILE_PATTERNS = [
    r"one file per",
    r"separate file",
    r"its own file",
    r"individual file",
    r"dedicated file",
    r"single file for (?:the|this|each) doc",
    r"new topic folder",
    r"new folder",
    r"per.document",
    r"one \.md file",
    r"one md file",
    r"named to match",
    r"alongside the pdf",
    r"never a combined",
    r"not a shared",
    r"not.*combined",
]
has_onefile = any(re.search(p, rl) for p in ONEFILE_PATTERNS)
if not has_onefile:
    print("FAIL: response does not recommend one-file-per-document convention", file=sys.stderr)
    print("Expected: separate/dedicated file per document (not a combined NOTES.md)", file=sys.stderr)
    sys.exit(1)

# --- Check 2: must NOT positively recommend a combined/shared notes approach ---
# Use context-aware check: look for "combined notes" WITHOUT a preceding negation
COMBINED_PATTERN = re.compile(
    r"(combined notes|shared notes|single notes file|one notes file|master notes|"
    r"aggregate.* notes|all.* notes.*file|notes\.md.*all|central notes|general notes)"
)
NEGATION_WORDS = ("never", "not", "don't", "avoid", "no ", "instead", "don't")

for m in COMBINED_PATTERN.finditer(rl):
    # Look at the 40 chars before the match for a negation word
    prefix = rl[max(0, m.start() - 40):m.start()]
    if any(neg in prefix for neg in NEGATION_WORDS):
        continue  # negated mention — not a recommendation
    print("FAIL: response recommends a combined notes approach (against the memory convention)", file=sys.stderr)
    print(f"  found: '...{rl[max(0,m.start()-20):m.end()+20]}...'", file=sys.stderr)
    sys.exit(1)

print("PASS: response recommends a separate file per document (not a combined notes file)")
sys.exit(0)
PY
