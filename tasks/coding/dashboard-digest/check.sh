#!/bin/bash
set -uo pipefail

# check.sh — dashboard-digest (coding, clean)
#
# Gate: run the repo's OWN pure unit test (tests/digest.test.ts on computeDigestBuckets)
# against the workspace the model produced. Exit 0 iff vitest passes. No dev server needed.
#
# CONTRACT NOTE: requires WORKSPACE_DIR (restored + `npm ci`-provisioned workspace).
# Drains the transcript on stdin (unused for scoring here).

cat >/dev/null  # drain transcript

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "FAIL: WORKSPACE_DIR not set or not a directory (harness contract extension required)" >&2
    exit 2
fi

CHECK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$WS/node_modules/vitest" ]; then
    echo "FAIL: node_modules/vitest missing in workspace — restore must run 'npm ci'" >&2
    exit 2
fi

# Vendor the frozen test (authored by us, not the model) so the model cannot alter it.
mkdir -p "$WS/tests"
cp "$CHECK_DIR/digest.test.ts" "$WS/tests/digest.test.ts"

cd "$WS" || { echo "FAIL: cannot cd to workspace" >&2; exit 1; }

if npx --no-install vitest run tests/digest.test.ts 2>&1; then
    echo "PASS: digest bucket unit tests passed"
    exit 0
else
    echo "FAIL: digest bucket unit tests failed" >&2
    exit 1
fi
