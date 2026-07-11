#!/bin/bash
set -euo pipefail

# check.sh for print-date task
# Reads transcript JSON from stdin.
# Passes if the result contains a `date` command invocation.

TRANSCRIPT=$(cat)

# Extract the result field from the transcript JSON
RESULT=$(echo "$TRANSCRIPT" | python3 -c "
import json, sys
try:
    obj = json.load(sys.stdin)
    print(obj.get('result', ''))
except Exception as e:
    print('', file=sys.stderr)
    sys.exit(1)
")

# Check that the result contains the word 'date'
if echo "$RESULT" | grep -qE '\bdate\b'; then
    echo "PASS: result contains 'date' command"
    exit 0
else
    echo "FAIL: result does not contain 'date' command"
    echo "Result was: $RESULT" >&2
    exit 1
fi
