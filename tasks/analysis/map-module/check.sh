#!/bin/bash
set -uo pipefail

# check.sh — analysis/map-module (dt-analyze)
# Objective assertion on the map text. A correct map of the project data pipeline must
# name: the entry point (getMergedProjects), BOTH upstream stages (getProjects AND
# readManual), the merge/combine step, and at least one real seam (the mutex, or the
# override whitelist). Anchored on real symbol names.

RESULT="$(python3 -c "import sys,json;
try: print(json.load(sys.stdin).get('result','') or '')
except Exception: print('')")"
LC="$(printf '%s' "$RESULT" | tr '[:upper:]' '[:lower:]')"
has() { printf '%s' "$LC" | grep -Eiq "$1"; }

entry=0;  has 'getmergedprojects' && entry=1
getproj=0; { has 'getprojects' || has 'projects\.ts'; } && getproj=1
manual=0; { has 'readmanual' || has 'manual\.ts'; } && manual=1
merge=0;  { has 'merge' || has 'combin' || has 'override'; } && merge=1
seam=0;   { has 'mutex' || has 'whitelist' || has 'concurren' || has 'lock'; } && seam=1

echo "signals: entry=$entry getProjects=$getproj readManual=$manual merge=$merge seam=$seam" >&2

if [ "$entry" -eq 1 ] && [ "$getproj" -eq 1 ] && [ "$manual" -eq 1 ] && [ "$merge" -eq 1 ] && [ "$seam" -eq 1 ]; then
    echo "PASS: map names the entry point, both stages, the merge step, and a real seam"
    exit 0
fi
echo "FAIL: map missed a required element of the pipeline" >&2
exit 1
