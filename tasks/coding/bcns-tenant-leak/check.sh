#!/bin/bash
set -uo pipefail

# check.sh — bcns-tenant-leak (coding, clean)
#
# Against WORKSPACE_DIR (bcns-mini, plain Node 22 ESM, no deps):
#   1. `npm test` passes (the model's own regression tests must run green).
#   2. Hidden forbidden-read tests (hidden/tenant-isolation.test.mjs, copied in here):
#      listJobs / searchJobs / exportJobs never return another client's row.
#   3. Structural (name-agnostic): exactly one top-level function in src/read-api.mjs
#      mentions `client_id`, and every reader reaches it directly or transitively.
#      Does NOT require new regression tests (the rubric scores those).
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
    printf '%s\n' "$out" | grep -E "^# (pass|fail)|^not ok" | head -12 >&2
    fail "hidden tenant-isolation tests failed (leak or fail-open on missing clientId)"
fi

# 3. structural: the client filter lives in exactly one top-level function, and every
#    reader reaches it (directly or through other top-level functions). Name-agnostic.
WS="$WS" node --input-type=module -e '
import { readFileSync } from "node:fs";
const src = readFileSync(process.env.WS + "/src/read-api.mjs", "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");
const die = (m) => { console.error(m); process.exit(1); };
// split into top-level segments at column-0 declarations
const startRe = /^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s*\*?\s*(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(async\s*)?(?:function\b|\([^)]*\)\s*=>|\w+\s*=>)|(?:const|let|var|class|import)\b)/;
const segs = []; let cur = { name: null, fn: false, text: "" };
for (const line of src.split("\n")) {
  const m = startRe.exec(line);
  if (m) { segs.push(cur); const name = m[1] || m[2] || null; cur = { name, fn: !!name, text: "" }; }
  cur.text += line + "\n";
}
segs.push(cur);
const fns = Object.fromEntries(segs.filter((x) => x.fn).map((x) => [x.name, x]));
for (const r of ["listJobs", "searchJobs", "exportJobs"]) if (!fns[r]) die(r + " missing from src/read-api.mjs");
const stray = segs.filter((x) => !x.fn && /client_id/.test(x.text));
if (stray.length) die("client_id referenced outside a top-level function");
const owners = Object.keys(fns).filter((n) => /client_id/.test(fns[n].text));
if (owners.length !== 1) die("client_id filter must live in exactly one function, found: " + (owners.join(", ") || "none"));
const owner = owners[0];
const calls = (n) => Object.keys(fns).filter((m) => m !== n && new RegExp("\\b" + m + "\\s*\\(").test(fns[n].text));
const reaches = (n, seen = new Set()) => {
  if (n === owner) return true;
  if (seen.has(n)) return false; seen.add(n);
  return calls(n).some((m) => reaches(m, seen));
};
for (const r of ["listJobs", "searchJobs", "exportJobs"]) if (!reaches(r)) die(r + " does not go through " + owner + " (the shared client filter)");
' || fail "structural check: every reader must go through the single shared client filter, with no separate client_id comparison"

echo "PASS: no reader leaks across clients; the client filter lives in one shared function"
exit 0
