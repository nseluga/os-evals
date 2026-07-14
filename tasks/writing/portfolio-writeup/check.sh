#!/bin/bash
set -uo pipefail

# check.sh — writing/portfolio-writeup (knowledge-routing + memory style)
# Objective proxy for Nate's portfolio style guide: short, no marketing buzzwords,
# concrete/evidence-driven.

RESULT="$(python3 -c "import sys,json;
try: print(json.load(sys.stdin).get('result','') or '')
except Exception: print('')")"

WS_RESULT="$RESULT" python3 - <<'PY'
import os, re, sys
text = os.environ.get("WS_RESULT", "")
lc = text.lower()

words = len(re.findall(r"[A-Za-z0-9:+/'-]+", text))
length_ok = 120 <= words <= 320

blacklist = [
    "cutting-edge", "cutting edge", "revolutionary", "seamless", "leverage",
    "passionate", "game-changing", "game changing", "state-of-the-art",
    "state of the art", "world-class", "world class", "synergy", "unlock",
    "supercharge", "robust solution", "powerful", "best-in-class",
]
hits = [b for b in blacklist if b in lc]
no_buzz = not hits

anchors = [
    "acute", "chronic", "acwr", "rolling", "window", "time-based", "time based",
    "leakage", "leak", "biomechanic", "workload", "feature pipeline",
]
specifics = sum(1 for a in anchors if a in lc)
has_number = bool(re.search(r"\b\d", text))
concrete = specifics >= 2 or (specifics >= 1 and has_number)

print(f"signals: words={words} length_ok={length_ok} buzz_hits={hits} "
      f"specifics={specifics} has_number={has_number}", file=sys.stderr)

if length_ok and no_buzz and concrete:
    print("PASS: short, buzzword-free, concrete portfolio writeup")
    sys.exit(0)
print("FAIL: writeup wrong length, used marketing buzzwords, or lacked concrete specifics",
      file=sys.stderr)
sys.exit(1)
PY
