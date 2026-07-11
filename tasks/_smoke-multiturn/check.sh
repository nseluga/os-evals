#!/bin/bash
set -euo pipefail

# check.sh for the multi-turn smoke test.
# Verifies the model produced the expected filesystem + git state in its workspace.
# Reads transcript JSON from stdin (ignored here); inspects WORKSPACE_DIR.
# rc: 0 = pass, 1 = task failure, 2 = infra/unscoreable (workspace not retained).

cat >/dev/null  # drain stdin (transcript) — this check is filesystem-based

if [ -z "${WORKSPACE_DIR:-}" ] || [ ! -d "$WORKSPACE_DIR" ]; then
    echo "INFRA: WORKSPACE_DIR missing or not retained (run with --keep-ws)" >&2
    exit 2
fi

if [ ! -f "$WORKSPACE_DIR/smoke.txt" ]; then
    echo "FAIL: smoke.txt not created in workspace" >&2
    exit 1
fi

if ! grep -q "SMOKE_OK" "$WORKSPACE_DIR/smoke.txt"; then
    echo "FAIL: smoke.txt does not contain SMOKE_OK" >&2
    echo "Contents: $(cat "$WORKSPACE_DIR/smoke.txt")" >&2
    exit 1
fi

# The workspace must be a real git repo (requirement 4 — branch/worktree tolerance).
if [ ! -e "$WORKSPACE_DIR/.git" ]; then
    echo "FAIL: workspace is not a git repo (_ensure_git_repo did not run)" >&2
    exit 1
fi

echo "PASS: smoke.txt=SMOKE_OK present in a git-repo workspace"
exit 0
