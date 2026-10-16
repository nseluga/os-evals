#!/bin/bash
set -uo pipefail
# check.sh — puzzles/schedule-optimum (text-only, reads transcript JSON on stdin). Seed 7 instance below.
# Verifies: all 8 jobs placed on M1/M2, no overlap per machine, precedence respected,
# declared makespan == real makespan == optimum (exhaustive search in gen.py).
# Exit: 0=PASS, 1=FAIL, 2=infra.
python3 -c '
import sys, json, re
DUR = {1: 7, 2: 2, 3: 8, 4: 7, 5: 3, 6: 4, 7: 2, 8: 3}      # job number -> duration
EDGES = [(3, 2), (3, 7), (4, 2), (4, 3), (4, 7), (5, 1), (6, 3), (8, 5), (8, 7)]    # (before, after)
OPT = 19
try:
    result = json.load(sys.stdin).get("result") or ""
except Exception as e:
    print(f"FAIL: could not parse transcript JSON: {e}", file=sys.stderr); sys.exit(2)
def fail(msg):
    print("FAIL: " + msg, file=sys.stderr); sys.exit(1)
t = result.replace("*", "").replace("`", "")
sched = {}  # last occurrence of each job wins (the final listing)
for j, m, s in re.findall(r"\bJ(\d+)\b[^\w\n]*(?:on|to|->|=>)?\W*M(\d)\b[^\d\n]*(\d+)", t, re.I):
    sched[int(j)] = (int(m), int(s))
ms = re.findall(r"makespan\W{0,12}(\d+)", t, re.I)
if set(sched) != set(DUR): fail(f"jobs scheduled {sorted(sched)}, need {sorted(DUR)}")
if any(m not in (1, 2) for m, _ in sched.values()): fail("machine must be M1 or M2")
if not ms: fail("no makespan= line")
for a, b in EDGES:
    if sched[b][1] < sched[a][1] + DUR[a]: fail(f"J{b} starts before J{a} finishes")
for m in (1, 2):
    iv = sorted((s, s + DUR[j], j) for j, (mm, s) in sched.items() if mm == m)
    for (s1, e1, j1), (s2, e2, j2) in zip(iv, iv[1:]):
        if s2 < e1: fail(f"J{j1} and J{j2} overlap on M{m}")
real = max(s + DUR[j] for j, (m, s) in sched.items())
if int(ms[-1]) != real: fail(f"declared makespan {ms[-1]} but schedule ends at {real}")
if real != OPT: fail(f"makespan {real}, optimum is {OPT}")
print(f"PASS: valid schedule, makespan {real}")
'
