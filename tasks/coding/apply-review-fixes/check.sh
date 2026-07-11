#!/bin/bash
set -uo pipefail

# check.sh — coding/apply-review-fixes (dt-fix)
# Filesystem assertion on the edited handler.py: all three review findings applied,
# behavior/signatures preserved.

cat >/dev/null  # drain transcript

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "FAIL: WORKSPACE_DIR not set or not a directory (harness contract required)" >&2
    exit 2
fi

H="$WS/handler.py"
fail() { echo "FAIL: $1" >&2; exit 1; }

[ -f "$H" ] || fail "handler.py missing from workspace"

# Finding 1: hardcoded secret removed, token read from environment
grep -q 'sk-live' "$H" && fail "hardcoded secret still present (finding 1 not fixed)"
grep -Eq 'os\.environ|getenv' "$H" || fail "token not read from environment (finding 1 not fixed)"

# Finding 2: no eval() on the payload
grep -Eq '\beval\s*\(' "$H" && fail "eval() still present (finding 2 not fixed)"

# Finding 3: request timeout added
grep -q 'timeout' "$H" || fail "requests.get still has no timeout (finding 3 not fixed)"

# Behavior guard: still valid Python and both functions preserved
python3 -c "import ast,sys; ast.parse(open('$H').read())" 2>/dev/null || fail "handler.py no longer parses as valid Python"
grep -q 'def parse_payload' "$H" || fail "parse_payload was removed"
grep -q 'def fetch' "$H" || fail "fetch was removed"

echo "PASS: all three review findings fixed; behavior/signatures preserved"
exit 0
