# Engineer Report
**Task:** Fix duplicate-run accumulation in runs/ — add cleanup step for *.json and *.trace.jsonl before matrix run
**Branch:** fix/harness-suite-defects
**Date:** 2026-07-13

## Design Decisions
- Minimal surgical change: two-line rm -f added immediately after mkdir -p, before any matrix execution — no new abstractions needed
- Uses $RUNS_DIR variable (already set on line 45) — no hardcoded paths
- Silent failure (2>/dev/null || true) matches existing shell conventions; missing files are not an error

## Files Changed
- `run.sh` — added cleanup echo + rm -f for *.json and *.trace.jsonl at line 50, after mkdir -p, before the os SHA stamp block

## Deferred / Out of Scope
- Did not add --no-clean flag; task scope did not request it
- Did not modify score.py glob behavior; fix is entirely in run.sh as specified

## Flags for Reviewer
- None; change is two lines with no logic branches
