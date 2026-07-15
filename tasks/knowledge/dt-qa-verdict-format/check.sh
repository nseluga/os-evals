#!/bin/bash
# check.sh — dt-qa-verdict-format
# Tests whether the model knows the VERDICT: PASS/FAIL machine-readable format
# and the distinction between "tests" and "tests+behavioral" gate modes.
set -uo pipefail

input=$(cat)

# PASS condition 1: must contain "VERDICT: PASS" or "VERDICT: FAIL" pattern
if ! echo "$input" | grep -qiE "VERDICT:\s*(PASS|FAIL)"; then
    echo "FAIL: response does not mention the exact VERDICT: PASS/FAIL format" >&2
    exit 1
fi

# PASS condition 2: must distinguish tests+behavioral as requiring more than just tests
# Accept keywords: behavioral, smoke, running, live, endpoint, server, real
if ! echo "$input" | grep -qiE "(behavioral|smoke.pass|live.server|real.server|running.app|hit.the.endpoint)"; then
    echo "FAIL: response does not describe what tests+behavioral adds beyond tests" >&2
    exit 1
fi

echo "PASS: response includes VERDICT format and tests+behavioral distinction"
exit 0
