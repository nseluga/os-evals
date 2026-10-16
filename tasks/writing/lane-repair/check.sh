#!/bin/bash
set -uo pipefail

# check.sh — writing/lane-repair
# Parses $WORKSPACE_DIR/LANE.md against the lane-md schema subset an unattended
# dev-team-auto run depends on. Exit 0 = no problems, 1 = problems listed on stdout,
# 2 = infra (WORKSPACE_DIR unset / not a directory).

cat >/dev/null  # drain transcript

WS="${WORKSPACE_DIR:-}"
if [ -z "$WS" ] || [ ! -d "$WS" ]; then
    echo "FAIL: WORKSPACE_DIR not set or not a directory (harness contract required)" >&2
    exit 2
fi
if [ ! -f "$WS/LANE.md" ]; then
    echo "FAIL: LANE.md missing from workspace"
    exit 1
fi

python3 -I - "$WS/LANE.md" <<'PY'
import re, sys

lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
problems = []

# --- split preamble / items / stop marker -------------------------------------
MARKER = re.compile(r"^>\s*\*{0,2}\s*⚠️?\s*AUTONOMOUS RUN\s*[—–-]+\s*STOP HERE\b")
item_starts = [i for i, l in enumerate(lines) if re.match(r"^- task:", l)]
marker_idx = [i for i, l in enumerate(lines) if MARKER.match(l)]
looks_like_marker = [i for i, l in enumerate(lines)
                     if re.search(r"AUTONOMOUS RUN|STOP HERE", l, re.I) and i not in marker_idx]

first_item = item_starts[0] if item_starts else len(lines)
pre = "\n".join(lines[:first_item])

# 1. Objective block (required top-level field)
m = re.search(r"^##\s+Objective\s*\n(.*?)(?=^##\s|\Z)", pre, re.S | re.M)
if not m or len(re.sub(r"\s+", " ", m.group(1)).strip()) < 20:
    problems.append("preamble: missing or empty '## Objective' block")

# 2. stop marker present and well-formed
if not marker_idx:
    problems.append("stop marker missing or malformed (need a line starting '> **⚠️ AUTONOMOUS RUN — STOP HERE')")
elif marker_idx[0] < first_item:
    problems.append("stop marker sits above every item (nothing would run)")
if len(marker_idx) > 1:
    problems.append("more than one stop marker")

if not item_starts:
    problems.append("no '- task:' items found")

# --- parse items ----------------------------------------------------------------
bounds = item_starts + [len(lines)]
items = []
for n, s in enumerate(item_starts):
    e = bounds[n + 1]
    for j in range(s + 1, e):  # an item ends at a stop marker line too
        if j in marker_idx or j in looks_like_marker:
            e = j
            break
    items.append((s, lines[s:e]))

ids = {}
for s, blk in items:
    label = f"item at line {s + 1}"
    text = "\n".join(blk)
    # fields: two-space-indented keys; bullets under guardrails / done when
    fields, cur = {}, None
    for l in blk[1:]:
        k = re.match(r"^  ([a-z][a-z -]*):\s*(.*)$", l)
        if k:
            cur = k.group(1).strip()
            fields[cur] = [k.group(2)] if k.group(2).strip() else []
        elif cur is not None and l.strip():
            fields[cur].append(l.strip())
    fields["task"] = [re.sub(r"^- task:\s*", "", blk[0])] + fields.get("task", [])
    # task continuation lines (indented, before the first key) belong to task
    for l in blk[1:]:
        if re.match(r"^  [a-z][a-z -]*:", l):
            break
        if l.strip():
            fields["task"].append(l.strip())

    for req in ("guardrails", "done when", "status"):
        if not fields.get(req):
            problems.append(f"{label}: missing or empty '{req}:'")
    if fields.get("status") and fields["status"][0].strip() != "not started":
        problems.append(f"{label}: status must be 'not started'")

    # unique ids
    if fields.get("id"):
        i = fields["id"][0].strip().strip("`'\"")
        ids.setdefault(i, []).append(label)

    # testable done-when: every criterion needs a concrete check cue
    CUE = re.compile(r"\b(tests?|exits?|return\w*|print\w*|files?|status|count|passes|passing|responds?|"
                     r"errors?|output|logs?|equals?|rows?)\b|≥|≤|==|\d", re.I)
    for b in fields.get("done when", []):
        b = re.sub(r"^-\s*", "", b)
        if not CUE.search(b):
            problems.append(f"{label}: done-when not testable: {b!r}")

    # guardrails must be prohibitions
    PROHIB = re.compile(r"\b(never|do not|don't|must not|not|no)\b", re.I)
    for b in fields.get("guardrails", []):
        b = re.sub(r"^-\s*", "", b)
        if re.match(r"^(try to|avoid|prefer|ideally|should|consider|where possible)\b", b, re.I) \
                or not PROHIB.search(b):
            problems.append(f"{label}: guardrail is not a prohibition: {b!r}")

    # caution / ui values
    for key in ("caution", "ui"):
        if key in fields and (not fields[key] or fields[key][0].strip().lower() != "true"):
            problems.append(f"{label}: '{key}:' must be 'true' or absent, got {' '.join(fields[key])!r}")

    # open questions
    if re.search(r"\bTBD\b|\bTODO\b|\?", text):
        problems.append(f"{label}: open question (TBD/TODO/'?') left in the item body")

for i, where in ids.items():
    if len(where) > 1:
        problems.append(f"duplicate item id {i!r}: " + ", ".join(where))

if problems:
    print(f"FAIL: {len(problems)} problem(s) in LANE.md")
    for p in problems:
        print(" -", p)
    sys.exit(1)
print("PASS: LANE.md satisfies the schema checks")
PY
exit $?
