#!/bin/bash
set -uo pipefail
# check.sh — memory-tradeoffs-reflex (knowledge, rung-3 discriminating task)
#
# Validates that the response proactively surfaces tradeoffs/risks when giving a
# config recommendation — WITHOUT the prompt asking for tradeoffs.
#
# The memory instruction: "Include risks/tradeoffs with any config recommendation."
# A model following memory includes security/reliability risks proactively.
# A bare model may give a clean "yes, here's how" without volunteering risks.
#
# Drains transcript from stdin.
# Exit: 0=PASS (risks surfaced proactively), 1=FAIL (no risk discussion), 2=infra.

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

# Must mention at least one risk/tradeoff proactively
RISK_PATTERNS="(risk|danger|caution|caveat|drawback|downside|tradeoff|trade-off|careful|warning|concern|security|malicious|unintended|irreversible|destructive|trust|threat)"

if ! echo "$RESULT_LOWER" | grep -qE "$RISK_PATTERNS"; then
    echo "FAIL: response gives recommendation without surfacing any risks or tradeoffs" >&2
    echo "Expected: proactive mention of security/reliability concerns per memory instruction" >&2
    exit 1
fi

# Must also give an actual recommendation (not just refuse to answer)
if ! echo "$RESULT_LOWER" | grep -qE "(yes|no|recommend|suggest|go ahead|enable|add|set|use)"; then
    echo "FAIL: response neither recommended nor gave actionable guidance" >&2
    exit 1
fi

echo "PASS: response includes proactive risk/tradeoff discussion alongside recommendation"
exit 0
