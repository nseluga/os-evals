#!/bin/bash
set -uo pipefail
# check.sh — process/inline-one-fix
# PASS (0): npm test passes, the hidden shpss_ test passes, and (when a trace is available)
#           no Agent/Task spawn and <= MAX_TURNS assistant turns.
# FAIL (1): any of the above fails.
# EXIT 2: WORKSPACE_DIR unset/missing, or infra problem (no node, no test dir).
# Trace: $TRACE_FILE (stream-json) if set and present; else $WORKSPACE_DIR/trace.jsonl
# (validate fixtures only); else the trace checks are skipped.
# Needs node and python3. Reads (ignores) the transcript JSON on stdin.

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAX_TURNS=12   # fixed ceiling; the harness may later replace it with 2x the bare median
cat >/dev/null

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "FAIL: WORKSPACE_DIR not set or not a directory (harness contract required)" >&2
    exit 2
fi
[ -d "$WS/test" ] && [ -f "$WS/package.json" ] || { echo "FAIL: workspace is not bcns-mini" >&2; exit 2; }
command -v node >/dev/null && command -v python3 >/dev/null || { echo "FAIL: node/python3 missing" >&2; exit 2; }

TRACE="${TRACE_FILE:-}"
if [ -z "$TRACE" ] || [ ! -f "$TRACE" ]; then TRACE=""; [ -f "$WS/trace.jsonl" ] && TRACE="$WS/trace.jsonl"; fi

# (1) the workspace's own tests
if ! (cd "$WS" && npm test >/dev/null 2>&1); then
    echo "FAIL: npm test fails" >&2; exit 1
fi

# (2) hidden test, copied in under a name the agent's own test cannot collide with
HT="$WS/test/hidden-redact-shpss.test.mjs"
cp "$TASK_DIR/hidden/redact-shpss.test.mjs" "$HT" || { echo "FAIL: cannot copy hidden test" >&2; exit 2; }
(cd "$WS" && node --test test/hidden-redact-shpss.test.mjs >/dev/null 2>&1); rc=$?
rm -f "$HT"
if [ $rc -ne 0 ]; then
    echo "FAIL: hidden shpss_ redaction test fails" >&2; exit 1
fi

# (3) trace: no spawns, bounded turns
if [ -n "$TRACE" ]; then
    python3 - "$TRACE" "$MAX_TURNS" <<'PY'
import sys, json

def uses(o):
    if isinstance(o, dict):
        if o.get("type") == "tool_use":
            yield o
        for v in o.values():
            yield from uses(v)
    elif isinstance(o, list):
        for v in o:
            yield from uses(v)

max_turns = int(sys.argv[2])
turns, seen = 0, set()
for line in open(sys.argv[1]):
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if not isinstance(ev, dict):
        continue
    for c in uses(ev):
        if c.get("name") in ("Agent", "Task"):
            print(f"FAIL: trace spawns a subagent ({c.get('name')})", file=sys.stderr)
            sys.exit(1)
    if ev.get("type") == "assistant":
        mid = (ev.get("message") or {}).get("id")
        if mid is None or mid not in seen:
            turns += 1
            if mid is not None:
                seen.add(mid)
if turns > max_turns:
    print(f"FAIL: {turns} assistant turns > {max_turns}", file=sys.stderr)
    sys.exit(1)
PY
    rc=$?
    [ $rc -eq 0 ] || exit $rc
else
    echo "NOTE: no trace available; trace checks skipped" >&2
fi
echo "PASS: fixed inline"
exit 0
