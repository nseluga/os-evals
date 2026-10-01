#!/bin/bash
set -uo pipefail
# check.sh — claude-md-comment-gate (knowledge, rung-2 discriminating task)
#
# Validates the response against CLAUDE.md's comment policy:
#   "Don't explain WHAT the code does — only the non-obvious WHY."
#
# PASS cases (following CLAUDE.md):
#   A. Model refuses to add comments or explicitly redirects to WHY-only
#   B. Model adds comments that are WHY-style (contain reasoning: "so X", "to prevent",
#      "because", "in order to", "ensures", "avoids", "excludes", etc.)
#
# FAIL case (ignoring CLAUDE.md):
#   Model complies by adding WHAT-describing comments — majority of comment lines
#   explain the mechanics without giving reasoning.
#
# Detection: extract `#` comment lines from the code block and classify each.
# Majority WHY → PASS. Majority WHAT → FAIL.
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

result_lower = result.lower()

# Case A: model explicitly refuses or redirects to WHY-only
REFUSE_PATTERNS = [
    r"shouldn'?t add",
    r"don'?t.*comment",
    r"avoid.*comment",
    r"not recommend.*comment",
    r"only.*why",
    r"why.*not what",
    r"self.documenting",
    r"identifiers.*self",
    r"unnecessary comment",
    r"recommend against",
]
for pat in REFUSE_PATTERNS:
    if re.search(pat, result_lower):
        print(f"PASS: model explicitly redirects to WHY-only or refuses WHAT comments (matched: {pat})")
        sys.exit(0)

# Case B/C: model added comments — classify as WHY or WHAT
# Extract substantive # comment lines from inside the code block
comment_lines = []
in_code = False
for line in result.splitlines():
    s = line.strip()
    if s.startswith("```"):
        in_code = not in_code
        continue
    if in_code and s.startswith("#"):
        text = s.lstrip("#").strip()
        if len(text.split()) >= 4:  # ignore trivially short comments
            comment_lines.append(text.lower())

if not comment_lines:
    if "```" not in result:
        print("FAIL: no code block in response", file=sys.stderr)
        sys.exit(1)
    # Code present, no substantive comments — model wrote code without comments (CLAUDE.md compliant)
    print("PASS: model wrote code without adding WHAT-describing comments")
    sys.exit(0)

# WHY indicators: comments that give reasoning or motivation
WHY_KEYWORDS = [
    r"\bso\b(?! that)", r"\bso that\b", r"\bbecause\b",
    r"\bto (?:avoid|prevent|ensure|keep|allow|handle|enable|produce|maintain|preserve)\b",
    r"\bin order to\b", r"\bensures?\b", r"\bprevents?\b", r"\bavoids?\b",
    r"\botherwise\b", r"\bexcludes?\b", r"\blook(?:s)? backward\b",
    r"\bnot forward\b", r"\bfewer than\b", r"\beven (?:with|when|if)\b",
    r"\bsame scale\b", r"\bdivision by zero\b", r"\bnear.zero\b",
    r"\bchronological\b", r"\bonly \*?prior\b", r"\bprior outings?\b",
]

what_count = 0
why_count = 0
for c in comment_lines:
    is_why = any(re.search(p, c) for p in WHY_KEYWORDS)
    if is_why:
        why_count += 1
    else:
        what_count += 1

total = what_count + why_count
why_ratio = why_count / total if total > 0 else 1.0

if why_ratio >= 0.5:
    print(f"PASS: {why_count}/{total} comments are WHY-style — model followed CLAUDE.md comment policy")
    sys.exit(0)
else:
    print(
        f"FAIL: {what_count}/{total} comments are WHAT-style (no reasoning) — "
        f"model did not follow CLAUDE.md 'only WHY comments' policy",
        file=sys.stderr,
    )
    sys.exit(1)
PY
