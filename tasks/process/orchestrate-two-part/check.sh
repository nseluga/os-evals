#!/bin/bash
set -uo pipefail
# check.sh — process/orchestrate-two-part
# PASS (0): (1) `npm test` passes in the workspace, with more tests than the 13 at base;
#           (2) the hidden acceptance tests for both items pass;
#           (3) when $TRACE_FILE (stream-json trace) is set and readable: >=2 build-worker
#               spawns (Agent/Task tool_use in assistant events, classified by subagent_type /
#               description only) and >=1 reviewer spawn in a later turn (message.id order)
#               than the second worker. Fix workers ("apply review findings") are ignored.
#               TRACE_FILE unset -> check 3 skipped; set but missing -> exit 2.
# FAIL (1): any of the above fails.
# EXIT 2: WORKSPACE_DIR unset/missing, TRACE_FILE set but missing, or node/npm/python3 unavailable.
# Non-gating: prints `signal:<name>=<value>` lines to stderr (worker-models, reviewer-model,
# parallel-spawns, worktree, visible-split-line).
# The transcript JSON on stdin is not used.

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cat >/dev/null

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "FAIL: WORKSPACE_DIR not set or not a directory (harness contract required)" >&2
    exit 2
fi
for bin in node npm python3; do
    command -v "$bin" >/dev/null 2>&1 || { echo "FAIL: $bin not available" >&2; exit 2; }
done
[ -f "$WS/package.json" ] || { echo "FAIL: workspace has no package.json" >&2; exit 2; }
if [ -n "${TRACE_FILE:-}" ] && [ ! -f "$TRACE_FILE" ]; then
    echo "FAIL: TRACE_FILE set but missing: $TRACE_FILE" >&2; exit 2
fi

fail=0

# (1) visible suite
NPM_OUT="$(cd "$WS" && npm test 2>&1)"; rc=$?
if [ "$rc" -ne 0 ]; then
    echo "FAIL: npm test failed" >&2; printf '%s\n' "$NPM_OUT" | tail -15 >&2; fail=1
else
    n="$(printf '%s\n' "$NPM_OUT" | sed -n 's/^# tests \([0-9][0-9]*\).*/\1/p' | tail -1)"
    if [ -z "$n" ] || [ "$n" -le 13 ]; then
        echo "FAIL: npm test passed but ran ${n:-?} tests (base has 13; new tests were required)" >&2; fail=1
    fi
fi

# (2) hidden tests, copied in under unlikely names and removed afterwards
HID=()
for f in "$TASK_DIR"/hidden/*.test.mjs; do
    d="$WS/test/zz-hidden-$(basename "$f")"; cp "$f" "$d"; HID+=("$d")
done
HOUT="$(cd "$WS" && node --test "${HID[@]}" 2>&1)"; rc=$?
rm -f "${HID[@]}"
if [ "$rc" -ne 0 ]; then
    echo "FAIL: hidden acceptance tests failed" >&2
    printf '%s\n' "$HOUT" | grep -E '^\s*(not ok|# fail|error:|message:)' | head -20 >&2; fail=1
fi

# (3) trace: orchestration shape, plus non-gating signals
python3 - "${TRACE_FILE:-}" <<'PY'
import sys, json, re, os

trace = sys.argv[1]
SIGS = ("worker-models", "reviewer-model", "parallel-spawns", "worktree", "visible-split-line")
if not trace:
    for s in SIGS:
        print(f"signal:{s}=n/a", file=sys.stderr)
    print("SKIP: TRACE_FILE unset; trace check skipped", file=sys.stderr)
    sys.exit(0)

# Only assistant events' message.content blocks are scanned. tool_result payloads and
# tool_use_result echoes (which can contain copies of Agent dicts) are never descended into.
# Nested subagent events are assistant events too, so they are included.
GENERIC = ("", "general-purpose", "claude", "worker")
NOT_BUILD_DESC = re.compile(r"find|search|locate|summar(?:ise|ize)|explain|explor|investigat|\bmap\b")
FIX_REVIEW = re.compile(r"\b(?:apply|fix|address|resolve)\b.{0,40}\breview")

def kind(inp):
    t = str(inp.get("subagent_type") or "").lower()
    d = str(inp.get("description") or "").lower()
    # A specific subagent_type decides; descriptions only disambiguate generic types.
    if re.search(r"review|audit", t):
        return "review"
    if re.search(r"engineer|\bui\b|build|implement", t):
        return "worker"
    if t not in GENERIC:
        return "other"          # Explore, Plan, analyzer, QA, ...
    if FIX_REVIEW.search(d):
        return "fix"            # applies review findings: neither a build worker nor a reviewer
    if re.search(r"\breview|\baudit", d):
        return "review"
    if NOT_BUILD_DESC.search(d):
        return "other"
    return "worker"             # generic agent, neutral description ("Item 1"): reads as a worker

events = []
for i, raw in enumerate(open(trace)):
    try:
        ev = json.loads(raw)
    except ValueError:
        continue
    if isinstance(ev, dict) and ev.get("type") == "assistant":
        msg = ev.get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            events.append((i, msg.get("id") or f"line{i}", [b for b in content if isinstance(b, dict)]))

# Order by turn (message.id, first appearance), not by line: one message can span lines.
turn = {}
for _, mid, _ in events:
    turn.setdefault(mid, len(turn))

workers, reviews, worktree = [], [], False
for i, mid, blocks in events:
    for b in blocks:
        if b.get("type") != "tool_use":
            continue
        inp = b.get("input") or {}
        if b.get("name") in ("Agent", "Task"):
            k = kind(inp)
            m = inp.get("model") or "default"
            if k == "worker":
                workers.append((turn[mid], i, mid, m))
            elif k == "review":
                reviews.append((turn[mid], i, mid, m))
            if inp.get("isolation") == "worktree":
                worktree = True
        elif b.get("name") == "Bash" and "git worktree add" in str(inp.get("command", "")):
            worktree = True
workers.sort(); reviews.sort()

# Heuristic: assistant text before the first worker turn that states a split.
SPLIT = re.compile(r"\bsplit|\bparallel|two (?:independent |separate )?(?:workers|pieces|parts|tasks|items|changes)|independent")
first_w = workers[0][0] if workers else None
split_line = any(
    b.get("type") == "text" and isinstance(b.get("text"), str) and SPLIT.search(b["text"].lower())
    for i, mid, blocks in events if first_w is None or turn[mid] < first_w for b in blocks)

per_turn = {}
for t, _, mid, _ in workers:
    per_turn[mid] = per_turn.get(mid, 0) + 1
parallel = any(c >= 2 for c in per_turn.values())
print("signal:worker-models=" + (",".join(w[3] for w in workers) or "none"), file=sys.stderr)
print("signal:reviewer-model=" + (",".join(r[3] for r in reviews) or "none"), file=sys.stderr)
print(f"signal:parallel-spawns={str(parallel).lower()}", file=sys.stderr)
print(f"signal:worktree={str(worktree).lower()}", file=sys.stderr)
print(f"signal:visible-split-line={str(split_line).lower()}", file=sys.stderr)

if len(workers) < 2:
    print(f"FAIL: trace shows {len(workers)} build-worker spawn(s); two separable items need >=2", file=sys.stderr)
    sys.exit(1)
second = workers[1][0]
# A review must start in a later turn than the second build worker. Later fix workers
# ("apply review findings") are allowed and ignored.
if not any(r[0] > second for r in reviews):
    print("FAIL: no reviewer spawn after the second build worker", file=sys.stderr)
    sys.exit(1)
print(f"trace ok: {len(workers)} workers, {len(reviews)} review spawn(s), review after second worker", file=sys.stderr)
PY
[ $? -eq 0 ] || fail=1

if [ "$fail" -ne 0 ]; then exit 1; fi
echo "PASS: suite green, hidden tests pass${TRACE_FILE:+, trace shape ok}"
exit 0
