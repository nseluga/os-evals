#!/bin/bash
set -uo pipefail

# check.sh — bcns-tenant-leak (coding, clean)
#
# Against WORKSPACE_DIR (bcns-mini, plain Node 22 ESM, no deps):
#   1. `npm test` passes (the model's own regression tests must run green).
#   2. Hidden forbidden-read tests (hidden/tenant-isolation.test.mjs, copied in here):
#      listJobs / searchJobs / exportJobs never return another client's row.
#   3. Structural: each reader calls scopedQuery, and `client_id` appears nowhere in
#      src/read-api.mjs outside scopedQuery's own body (one place owns the filter).
#
# rc: 0 = pass, 1 = real task failure, 2 = infra/unscoreable.

cat >/dev/null  # drain transcript on stdin (unused)

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "INFRA: WORKSPACE_DIR not set or not a directory" >&2
    exit 2
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "INFRA: node/npm not found" >&2
    exit 2
fi

CHECK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HIDDEN="$CHECK_DIR/hidden/tenant-isolation.test.mjs"
if [ ! -f "$HIDDEN" ] || [ ! -f "$WS/package.json" ]; then
    echo "INFRA: hidden test or workspace package.json missing" >&2
    exit 2
fi

fail() { echo "FAIL: $*" >&2; exit 1; }

# 1. the workspace's own suite (includes whatever tests the model added)
(cd "$WS" && npm test --silent >/tmp/bcns-tl-npm.$$ 2>&1) || { tail -15 /tmp/bcns-tl-npm.$$ >&2; rm -f /tmp/bcns-tl-npm.$$; fail "npm test failed"; }
rm -f /tmp/bcns-tl-npm.$$

# 2. hidden forbidden-read tests
mkdir -p "$WS/test"
HT="$WS/test/zz-hidden-tenant-isolation.test.mjs"
cp "$HIDDEN" "$HT"
out="$(cd "$WS" && node --test "$HT" 2>&1)"; rc=$?
rm -f "$HT"
if [ "$rc" -ne 0 ]; then
    printf '%s\n' "$out" | grep -E "^# (pass|fail)|not ok|leaked|Error" | head -12 >&2
    fail "hidden tenant-isolation tests failed (a reader returned another client's rows)"
fi

# 3. structural: the client filter lives in one place
WS="$WS" node --input-type=module -e '
import { readFileSync } from "node:fs";
let src = readFileSync(process.env.WS + "/src/read-api.mjs", "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");
const body = (name) => {
  const m = src.match(new RegExp("function\\s+" + name + "\\s*\\([^]*?\\n\\}"));
  return m ? m[0] : null;
};
const sq = body("scopedQuery");
if (!sq) { console.error("scopedQuery missing from src/read-api.mjs"); process.exit(1); }
for (const r of ["listJobs", "searchJobs", "exportJobs"]) {
  const b = body(r);
  if (!b) { console.error(r + " missing from src/read-api.mjs"); process.exit(1); }
  if (!/scopedQuery\s*\(/.test(b)) { console.error(r + " does not call scopedQuery"); process.exit(1); }
}
const rest = src.replace(sq, "");
if (/client_id/.test(rest)) { console.error("client_id referenced outside scopedQuery (duplicate tenant filter)"); process.exit(1); }
' || fail "structural check: every reader must go through scopedQuery, with no separate client_id comparison"

echo "PASS: no reader leaks across clients; the filter lives in scopedQuery"
exit 0
