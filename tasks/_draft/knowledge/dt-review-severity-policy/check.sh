#!/bin/bash
# check.sh — dt-review-severity-policy
# Tests whether the model knows that Critical AND Important block exit (require re-QA),
# while Minor findings are applied without looping.
set -uo pipefail

input=$(cat)

# PASS condition 1: both Critical and Important must be named as blocking
if ! echo "$input" | grep -qi "critical"; then
    echo "FAIL: response does not mention Critical as blocking" >&2
    exit 1
fi
if ! echo "$input" | grep -qi "important"; then
    echo "FAIL: response does not mention Important as blocking" >&2
    exit 1
fi

# PASS condition 2: Minor must be described as non-blocking (applied without re-QA)
# Accept: "minor", "without looping", "applied once", "don't block", "not block", "skip re-qa"
if ! echo "$input" | grep -qi "minor"; then
    echo "FAIL: response does not mention Minor severity" >&2
    exit 1
fi

# PASS condition 3: Minor must be distinguished as NOT requiring a re-QA pass
# Negative check: if the response says minor ALSO loops or requires re-QA, fail
if echo "$input" | grep -qi "minor.*loop\|minor.*re-qa\|minor.*block\|minor.*require.*qa"; then
    echo "FAIL: response incorrectly says Minor findings require a QA loop" >&2
    exit 1
fi

# PASS condition 4: Minor must be described as applied (dt-fix applies them)
if ! echo "$input" | grep -qiE "(minor.*(applied|fix|once|without|skip)|applied.*minor|(dt-fix|fixer).*minor|minor.*(dt-fix|fixer))"; then
    echo "FAIL: response does not describe Minor as applied without looping" >&2
    exit 1
fi

echo "PASS: response correctly distinguishes Critical/Important (blocking) from Minor (applied, no loop)"
exit 0
