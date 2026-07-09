#!/bin/bash
set -uo pipefail

# check.sh — dashboard-inbox (coding, clean)
#
# Gate: run the repo's OWN behavioral test (tests/inbox-ui.test.ts) against the
# workspace the model produced. Exit 0 iff vitest passes.
#
# CONTRACT NOTE: requires WORKSPACE_DIR (restored + `npm ci`-provisioned workspace).
# See CONTRACT-NOTE.md. Drains the transcript on stdin (not used for scoring here).
# STATUS: NEEDS-VALIDATION — confirm this test passes on solution commit c8dee19/10db84a
# from base 5a4c800 before trusting it as a gate (see meta.yaml).

cat >/dev/null  # drain transcript

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "FAIL: WORKSPACE_DIR not set or not a directory (harness contract extension required)" >&2
    exit 2
fi

CHECK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# node toolchain must be provisioned in the restored workspace
if [ ! -d "$WS/node_modules/vitest" ]; then
    echo "FAIL: node_modules/vitest missing in workspace — restore must run 'npm ci'" >&2
    exit 2
fi

# Vendor the frozen test (authored by us, not the model) into the workspace so the
# model cannot have altered/deleted it.
mkdir -p "$WS/tests"
cp "$CHECK_DIR/inbox-ui.test.ts" "$WS/tests/inbox-ui.test.ts"

cd "$WS" || { echo "FAIL: cannot cd to workspace" >&2; exit 1; }

# Run only the vendored inbox test.
if npx --no-install vitest run tests/inbox-ui.test.ts 2>&1; then
    echo "PASS: inbox-ui behavioral test suite passed"
    exit 0
else
    echo "FAIL: inbox-ui behavioral test suite failed" >&2
    exit 1
fi
