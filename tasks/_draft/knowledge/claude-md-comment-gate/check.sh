#!/bin/bash
set -uo pipefail
# check.sh — claude-md-comment-gate (knowledge, rung-2 discriminating task)
#
# Validates that the response follows the CLAUDE.md comment policy:
#   "Don't explain WHAT the code does — only the non-obvious WHY."
#
# A model following CLAUDE.md should refuse to add WHAT comments, redirect to WHY-only,
# or explain why such comments are not recommended. A bare model will produce a commented
# version of the function.
#
# Drains transcript from stdin.
# Exit: 0=PASS (refused or redirected to WHY-only), 1=FAIL (added WHAT comments), 2=infra.

TRANSCRIPT="$(cat)"

RESULT="$(echo "$TRANSCRIPT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('result', ''))
except Exception as e:
    print('', file=sys.stderr)
    sys.exit(2)
" 2>&1)"

if [ $? -ne 0 ]; then
    echo "FAIL: could not parse transcript JSON" >&2
    exit 2
fi

RESULT_LOWER="$(echo "$RESULT" | tr '[:upper:]' '[:lower:]')"

# FAIL if the model just added WHAT comments without pushback.
# Signs: added comments that describe what lines do WITHOUT recommending against them.
# Strong signal: response contains code block WITH line-level comments AND no pushback text.

HAS_WHAT_COMMENTS=0
# If response has a code block with # comments describing the code steps
if echo "$RESULT" | grep -qE "^(#.*sort|#.*group|#.*rolling|#.*window|#.*sum|#.*compute|#.*calculat|#.*return|#.*shift|#.*clip|#.*chronic|#.*acute|#.*convert)"; then
    HAS_WHAT_COMMENTS=1
fi

HAS_PUSHBACK=0
# Response pushes back on adding WHAT comments or redirects to WHY-only
if echo "$RESULT_LOWER" | grep -qE "(not recommend|avoid|shouldn't|don't.*comment|no.*comment|why.*not what|what.*not useful|identifiers.*self|self.documenting|unnecessary comment|instead.*why|only.*why|when.*why)"; then
    HAS_PUSHBACK=1
fi

if [ "$HAS_WHAT_COMMENTS" -eq 1 ] && [ "$HAS_PUSHBACK" -eq 0 ]; then
    echo "FAIL: model added WHAT comments without recommending against them" >&2
    echo "Expected: refusal or redirect to WHY-only comments per CLAUDE.md policy" >&2
    exit 1
fi

if [ "$HAS_PUSHBACK" -eq 1 ]; then
    echo "PASS: response correctly recommends against WHAT comments or redirects to WHY-only"
    exit 0
fi

# If neither WHAT comments nor clear pushback, check for general decline
if echo "$RESULT_LOWER" | grep -qE "(wouldn't|would not|i don't think|not a good idea|not helpful|not needed|not necessary)"; then
    echo "PASS: response appropriately declines to add WHAT comments"
    exit 0
fi

echo "FAIL: response neither refused WHAT comments nor pushed back on the approach" >&2
echo "Result preview: $(echo "$RESULT" | head -5)" >&2
exit 1
