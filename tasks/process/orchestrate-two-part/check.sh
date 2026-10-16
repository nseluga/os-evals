#!/bin/bash
set -uo pipefail
# check.sh — process/orchestrate-two-part
# PASS (0): (1) `npm test` passes in the workspace, with more tests than the 13 at base;
#           (2) the hidden acceptance tests for both items pass;
#           (3) when $TRACE_FILE (stream-json trace) is set and readable: >=2 worker spawns
#               (Agent/Task tool_use reading as builder/worker) and >=1 reviewer spawn on a
#               trace line AFTER the last worker spawn. Trace unset/missing -> check 3 skipped.
# FAIL (1): any of the above fails.
# EXIT 2: WORKSPACE_DIR unset/missing, or node/npm/python3 unavailable.
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
if not trace or not os.path.isfile(trace):
    for s in SIGS:
        print(f"signal:{s}=n/a", file=sys.stderr)
    print("SKIP: TRACE_FILE unset or missing; trace check skipped", file=sys.stderr)
    sys.exit(0)

def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)

NOT_WORKER = re.compile(r"explore|plan|analy|qa|statusline|guide|learn|research")
BUILD_WORDS = re.compile(r"implement|build|engineer|worker|\badd\b|write|modify|edit|fix|code|feature")
GENERIC = ("", "general-purpose", "claude", "worker")

def kind(inp):
    t = str(inp.get("subagent_type") or "").lower()
    d = str(inp.get("description") or "").lower()
    p = str(inp.get("prompt") or "").lower()
    if re.search(r"review|audit", t) or (t in GENERIC and re.search(r"\breview|\baudit", d)):
        return "review"
    if NOT_WORKER.search(t):
        return "other"
    if re.search(r"engineer|build|implement|worker", t) or re.search(r"implement|build|engineer|worker", d):
        return "worker"
    if t in GENERIC and BUILD_WORDS.search(d + " " + p):
        return "worker"
    return "other"

workers, reviews, bash_wt, split_line = [], [], False, False
first_worker_idx = None
lines = []
for i, raw in enumerate(open(trace)):
    try:
        lines.append((i, json.loads(raw)))
    except ValueError:
        continue

for i, ev in lines:
    for o in walk(ev):
        if o.get("type") != "tool_use":
            continue
        inp = o.get("input") or {}
        name = o.get("name")
        if name in ("Agent", "Task"):
            k = kind(inp)
            m = inp.get("model") or "default"
            if k == "worker":
                workers.append((i, m))
                if first_worker_idx is None:
                    first_worker_idx = i
            elif k == "review":
                reviews.append((i, m))
            if inp.get("isolation") == "worktree":
                bash_wt = True
        elif name == "Bash" and "git worktree add" in str(inp.get("command", "")):
            bash_wt = True

# Heuristic: an assistant text block before the first worker spawn that states a split.
SPLIT = re.compile(r"\bsplit|\bparallel|two (?:independent |separate )?(?:workers|pieces|parts|tasks|items|changes)|independent")
for i, ev in lines:
    if first_worker_idx is not None and i >= first_worker_idx:
        break
    for o in walk(ev):
        if o.get("type") == "text" and isinstance(o.get("text"), str) and SPLIT.search(o["text"].lower()):
            split_line = True

per_line = {}
for i, _ in workers:
    per_line[i] = per_line.get(i, 0) + 1
parallel = any(c >= 2 for c in per_line.values())
print("signal:worker-models=" + (",".join(m for _, m in workers) or "none"), file=sys.stderr)
print("signal:reviewer-model=" + (",".join(m for _, m in reviews) or "none"), file=sys.stderr)
print(f"signal:parallel-spawns={str(parallel).lower()}", file=sys.stderr)
print(f"signal:worktree={str(bash_wt).lower()}", file=sys.stderr)
print(f"signal:visible-split-line={str(split_line).lower()}", file=sys.stderr)

if len(workers) < 2:
    print(f"FAIL: trace shows {len(workers)} worker spawn(s); two separable items need >=2", file=sys.stderr)
    sys.exit(1)
last_worker = max(i for i, _ in workers)
if not any(i > last_worker for i, _ in reviews):
    print("FAIL: no reviewer spawn after the last worker spawn", file=sys.stderr)
    sys.exit(1)
print(f"trace ok: {len(workers)} workers, {len(reviews)} review spawn(s), review after last worker", file=sys.stderr)
PY
[ $? -eq 0 ] || fail=1

if [ "$fail" -ne 0 ]; then exit 1; fi
echo "PASS: suite green, hidden tests pass${TRACE_FILE:+, trace shape ok}"
exit 0
