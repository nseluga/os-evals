#!/bin/bash
set -uo pipefail

# check.sh — pathguard-resolver (coding, clean)
#
# Gate: run the vendored security+correctness battery (test_pathguard.py) against the
# src/pathguard package the model wrote in WORKSPACE_DIR. Pure stdlib python; no server,
# no network. The test file is vendored (copied in at check time) so the model can't edit it.
#
# Quality dimension: SECURITY (path traversal, absolute-path/NUL validation, symlink
# escape, sibling-prefix bypass, no shell-out) + functional correctness.
#
# rc: 0 = pass, 1 = real task failure, 2 = infra/unscoreable (WORKSPACE_DIR unset).

cat >/dev/null  # drain transcript on stdin (unused; this is a filesystem/unit check)

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "INFRA: WORKSPACE_DIR not set or not a directory" >&2
    exit 2
fi

CHECK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WORKSPACE_DIR="$WS" python3 "$CHECK_DIR/test_pathguard.py"
rc=$?
if [ "$rc" -eq 0 ]; then
    echo "PASS: pathguard security+correctness battery passed"
fi
exit $rc
