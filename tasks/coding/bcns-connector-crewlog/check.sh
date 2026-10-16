#!/bin/bash
set -uo pipefail

# check.sh — bcns-connector-crewlog (coding, clean)
#
# Runs against the restored bcns-mini workspace (WORKSPACE_DIR), Node 22 ESM, zero deps.
#   1. `npm test` passes (includes the base test that the three source lists agree
#      and whatever tests the model wrote).
#   2. hidden/crewlog.test.mjs is copied into test/ and run. It reaches the connector
#      through SOURCES, so the model's file naming is free. Covers decimal rounding,
#      null status, numeric id, non-UTC local day, Bearer redaction.
#   3. `crewlog` is present in all three registration sites: SOURCES (src/index.mjs),
#      ALLOWED_SOURCES (scripts/add-source.mjs), the source enum in api/contract.json.
# Every check runs and every failure is reported.
#
# rc: 0 = pass, 1 = real task failure, 2 = infra/unscoreable.

cat >/dev/null  # drain transcript on stdin (unused)

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "INFRA: WORKSPACE_DIR not set or not a directory" >&2
    exit 2
fi
CHECK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HIDDEN="$CHECK_DIR/hidden/crewlog.test.mjs"
if [ ! -f "$HIDDEN" ] || ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "INFRA: hidden test, node or npm missing" >&2
    exit 2
fi
# The workspace must be a bcns-mini checkout at all (a deleted package.json is a task failure,
# but an empty/unrestored dir is infra).
if [ ! -d "$WS/src" ] && [ ! -f "$WS/package.json" ]; then
    echo "INFRA: workspace looks unrestored (no src/ or package.json)" >&2
    exit 2
fi

cd "$WS" || exit 2
fails=()

# 1. repo test suite
if npm test >/tmp/crewlog-npm-test.$$ 2>&1; then
    echo "ok: npm test"
else
    fails+=("npm test failed")
    grep -E "^not ok|^# (pass|fail)|Error" /tmp/crewlog-npm-test.$$ | head -15 >&2
fi
rm -f /tmp/crewlog-npm-test.$$

# 2. hidden acceptance test, then remove it so the judged workspace stays clean
mkdir -p test
HT="test/zz-hidden-crewlog.test.mjs"
cp "$HIDDEN" "$HT"
if node --test "$HT" >/tmp/crewlog-hidden.$$ 2>&1; then
    echo "ok: hidden crewlog test"
else
    fails+=("hidden crewlog test failed")
    grep -E "^# (fail|pass)|not ok|Error|expected|actual|message" /tmp/crewlog-hidden.$$ | head -25 >&2
fi
rm -f /tmp/crewlog-hidden.$$ "$HT"

# 3. three registration sites
reg=$(node --input-type=module -e '
import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
const miss = [];
try { const { SOURCES } = await import(pathToFileURL("./src/index.mjs").href); if (!SOURCES.crewlog) miss.push("SOURCES"); } catch (e) { miss.push("SOURCES(" + e.message + ")"); }
try { const { ALLOWED_SOURCES } = await import(pathToFileURL("./scripts/add-source.mjs").href); if (!ALLOWED_SOURCES.includes("crewlog")) miss.push("ALLOWED_SOURCES"); } catch (e) { miss.push("ALLOWED_SOURCES(" + e.message + ")"); }
try { const c = JSON.parse(readFileSync("./api/contract.json", "utf8")); if (!c.definitions.Job.properties.source.enum.includes("crewlog")) miss.push("contract.json enum"); } catch (e) { miss.push("contract.json(" + e.message + ")"); }
console.log(miss.join(", "));
' 2>&1)
if [ -z "$reg" ]; then
    echo "ok: crewlog registered in SOURCES, ALLOWED_SOURCES, contract.json"
else
    fails+=("crewlog missing from: $reg")
fi

if [ ${#fails[@]} -eq 0 ]; then
    echo "PASS: bcns-connector-crewlog (npm test, hidden test, three registrations)"
    exit 0
fi
printf 'FAIL: %s\n' "${fails[@]}" >&2
exit 1
