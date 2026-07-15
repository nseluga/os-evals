#!/bin/bash
set -uo pipefail
# check.sh — memory-notes-format (knowledge, rung-3 discriminating task)
#
# Validates that the response follows the documented library-notes memory convention:
#   1. One file per document (never a combined NOTES.md)
#   2. Do not stub the file before reading the source
#
# Drains transcript from stdin, checks the text result.
# Exit: 0=PASS, 1=FAIL (wrong answer), 2=infra error.

TRANSCRIPT="$(cat)"

# Extract the result text from the JSON transcript
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

# Must recommend a SEPARATE file per document (not combined/aggregated)
if ! echo "$RESULT_LOWER" | grep -qE "(one file per|separate file|its own file|individual file|dedicated file|single file for (the|this|each) doc)"; then
    echo "FAIL: response does not recommend one-file-per-document convention" >&2
    echo "Expected: separate file per document (not combined NOTES.md)" >&2
    exit 1
fi

# Must NOT recommend a combined/shared notes file as the approach
if echo "$RESULT_LOWER" | grep -qE "(combined notes|shared notes|single notes|one notes|master notes|aggregate.* notes|all.* notes.*file|notes\.md.*all|central notes)"; then
    echo "FAIL: response recommends a combined notes approach (against the memory convention)" >&2
    exit 1
fi

# Should advise reading BEFORE writing stubs/structure
if echo "$RESULT_LOWER" | grep -qE "(stub|set up.*before.*read|creat.*before.*read|structur.*before.*read)"; then
    echo "FAIL: response recommends stubbing the file before reading (against memory: 'never write stubs before reading the source')" >&2
    exit 1
fi

echo "PASS: response follows the one-file-per-document convention and read-first approach"
exit 0
