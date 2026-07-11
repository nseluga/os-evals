#!/bin/bash
set -uo pipefail

# check.sh — analysis/qa-failing-test (dt-qa)
# The model wrote test_solution.py. It PASSES iff that test DISCRIMINATES: fails on the
# canonical buggy impl and passes on the canonical fixed impl. A happy-path-only test
# passes on both -> does not discriminate -> task fails.

cat >/dev/null  # drain transcript

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "FAIL: WORKSPACE_DIR not set or not a directory (harness contract required)" >&2
    exit 2
fi

CHECK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST="$WS/test_solution.py"

if [ ! -f "$TEST" ]; then
    echo "FAIL: model did not write test_solution.py to the workspace root" >&2
    exit 1
fi

run_against() {
    # $1 = canonical impl file to install as bank.py
    local impl="$1" tmp rc
    tmp="$(mktemp -d)"
    cp "$TEST" "$tmp/test_solution.py"
    cp "$impl" "$tmp/bank.py"
    ( cd "$tmp" && python3 test_solution.py ) >/dev/null 2>&1
    rc=$?
    rm -rf "$tmp"
    return $rc
}

run_against "$CHECK_DIR/bank_buggy.py"; buggy_rc=$?
run_against "$CHECK_DIR/bank_fixed.py"; fixed_rc=$?

echo "signals: buggy_rc=$buggy_rc (want !=0)  fixed_rc=$fixed_rc (want 0)" >&2

if [ "$fixed_rc" -eq 0 ] && [ "$buggy_rc" -ne 0 ]; then
    echo "PASS: test discriminates — fails the buggy impl, passes the correct one"
    exit 0
fi
echo "FAIL: test does not discriminate the planted contract bug" >&2
exit 1
