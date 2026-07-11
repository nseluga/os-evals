#!/bin/bash
set -uo pipefail

# check.sh — analysis/usage-audit (ai-usage-optimizer)
# Objective assertion against an authored answer key:
#   (1) names dev-team / dt-* as the under-used subsystem, AND
#   (2) recommends a top-tier reasoning model (opus, or at least sonnet) for the
#       refactor and does NOT recommend haiku for it.

RESULT="$(python3 -c "import sys,json;
try: print(json.load(sys.stdin).get('result','') or '')
except Exception: print('')")"
LC="$(printf '%s' "$RESULT" | tr '[:upper:]' '[:lower:]')"
has() { printf '%s' "$LC" | grep -Eiq "$1"; }

# (1) under-used subsystem = dev-team / dt-*
underused=0
if has 'dev.?team' || has '\bdt-' || has 'dt-\*' || has 'multi-agent'; then underused=1; fi

# (2) model recommendation: opus/sonnet good, haiku for the refactor is wrong
model_ok=0
if has '\bopus\b' || has '\bsonnet\b'; then model_ok=1; fi
haiku_for_refactor=0
# crude but effective: if haiku appears within the same answer AND opus/sonnet do NOT,
# treat as the wrong pick. If opus/sonnet are present, assume haiku is being ruled out.
if has '\bhaiku\b' && ! has '\bopus\b' && ! has '\bsonnet\b'; then haiku_for_refactor=1; fi

echo "signals: underused=$underused model_ok=$model_ok haiku_wrong=$haiku_for_refactor" >&2

if [ "$underused" -eq 1 ] && [ "$model_ok" -eq 1 ] && [ "$haiku_for_refactor" -eq 0 ]; then
    echo "PASS: audit names dev-team as under-used and picks a reasoning-grade model"
    exit 0
fi
echo "FAIL: audit missed the under-used subsystem or made a wrong model call" >&2
exit 1
