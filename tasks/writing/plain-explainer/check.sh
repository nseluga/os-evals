#!/bin/bash
set -uo pipefail

# check.sh — writing/plain-explainer (memory behavior: plain-English + tradeoffs)
# PASS iff (1) a plain-English definition appears early (hook = something that RUNS on an
# EVENT / automatically) AND (2) at least one concrete tradeoff/drawback is surfaced.

RESULT="$(python3 -c "import sys,json;
try: print(json.load(sys.stdin).get('result','') or '')
except Exception: print('')")"

WS_RESULT="$RESULT" python3 - <<'PY'
import os, re, sys
text = os.environ.get("WS_RESULT", "")
lc = text.lower()
words = re.findall(r"[A-Za-z0-9_'-]+", lc)
early = " ".join(words[:90])

def has(pat, s=lc): return re.search(pat, s) is not None

# (1) plain-English definition early: a hook RUNS (script/command/shell) on an EVENT
runs = any(w in early for w in ["run", "runs", "execute", "executes", "trigger", "triggers", "fires"])
event = any(w in early for w in ["event", "when", "before", "after", "on save", "automatically", "every time", "each time"])
mechanism = any(w in early for w in ["command", "script", "shell", "hook is"])
plain = runs and event and mechanism

# (2) at least one concrete tradeoff/drawback of auto-format-on-save
tradeoff = (
    has(r"slow") or has(r"block") or has(r"delay") or has(r"latenc") or
    has(r"silent") or has(r"opaque") or has(r"hide[sn]?\b|hidden") or
    has(r"surpris") or has(r"unexpected") or has(r"noisy diff|large diff|big diff|reformat") or
    has(r"fail") or has(r"debug") or has(r"conflict") or has(r"drawback|downside|tradeoff|trade-off|cons\b|caveat|risk")
)

print(f"signals: plain={plain} (runs={runs} event={event} mech={mechanism}) tradeoff={tradeoff}",
      file=sys.stderr)

if plain and tradeoff:
    print("PASS: plain-English definition up front and a concrete tradeoff surfaced")
    sys.exit(0)
print("FAIL: missing a plain early definition or any surfaced tradeoff", file=sys.stderr)
sys.exit(1)
PY
