#!/bin/bash
set -uo pipefail

# check.sh — analysis/review-flaw (dt-review)
# Objective assertion on the final review text. The review must catch the critical
# SQL-injection flaw AND at least one more real issue (hardcoded secret OR the
# quadratic nested-loop join). Convention-agnostic: matches on the CONCEPT, several
# synonyms each, so it rewards a correct review, not specific wording.

RESULT="$(python3 -c "import sys,json;
try: print(json.load(sys.stdin).get('result','') or '')
except Exception: print('')")"
LC="$(printf '%s' "$RESULT" | tr '[:upper:]' '[:lower:]')"

has() { printf '%s' "$LC" | grep -Eiq "$1"; }

# Critical: SQL injection
sqli=0
if has 'sql injection' || has 'injection' || has 'parameteri[sz]' || has 'sql.?inject' || \
   { has 'placeholder' && has 'query'; } || has 'unsanitized.*(query|sql|input)'; then sqli=1; fi

# Secondary A: hardcoded secret
secret=0
if has 'hard.?coded' || has 'secret' || has 'api.?key' || has 'credential' || has 'sk-live' || has 'in source'; then secret=1; fi

# Secondary B: quadratic / nested-loop inefficiency
perf=0
if has 'o\(n' || has 'quadratic' || has 'nested loop' || has 'n\*m' || has 'n\^2' || \
   { has 'dict' && has 'lookup'; } || has 'inefficient' && has 'loop'; then perf=1; fi

echo "signals: sqli=$sqli secret=$secret perf=$perf" >&2

if [ "$sqli" -eq 1 ] && [ $((secret + perf)) -ge 1 ]; then
    echo "PASS: review flagged SQL injection plus at least one more real issue"
    exit 0
fi
echo "FAIL: review missed the critical injection or lacked a second real issue" >&2
exit 1
