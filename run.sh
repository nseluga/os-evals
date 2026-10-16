#!/bin/bash
set -euo pipefail

# run.sh — top-level orchestrator for one iteration of the eval matrix.
#
# Builds configs from a git snapshot of ~/os at --os-sha, runs task x layer x model against
# frozen workspaces, scores every run, and renders a markdown scorecard.
#
# Usage:
#   ./run.sh                              # bare vs full at ~/os HEAD, opus
#   ./run.sh --layers bare,claude-md,memory,skills,full   # the ladder
#   ./run.sh --os-sha A --os-sha B        # A/B: full@A vs full@B
#   ./run.sh --tasks a,b --models opus,sonnet --max-budget-usd 1.50
#   ./run.sh --dry-run                    # build configs (free), print the matrix, exit
#   ./run.sh --no-build                   # reuse existing configs/<sha>/
#   ./run.sh --no-home-isolation          # claude keeps the real HOME (~/os = live)
#   ./run.sh --jobs 4                     # one-shot tasks 4 at a time; multi-turn stay serial
#   ./run.sh --ws-root /some/dir          # workspace root (default $EVAL_WS_ROOT or /Users/Shared/evalws)
#   ./run.sh --clean-ws                   # delete this invocation's workspaces after the scorecard
#   ./run.sh --repeat 3                   # run every task 3x (overrides each meta.yaml `repeat`)
#
# Each run gets <ws-root>/w-<hex>/ with w/ (its cwd) and cfg/ (its own CLAUDE_CONFIG_DIR,
# a clean copy of configs/<sha>/<layer>/), so no run can read another run's transcripts.
#
# Prior runs/ transcripts (and any workspaces physically inside runs/) are moved to
# runs/archive/<utc-ts>/ (never deleted); workspaces in an external ws-root stay put.
# So a scorecard only ever covers the run that just happened.
#
# Outputs:
#   scorecards/{timestamp}-{os-sha}.md   the scorecard
#   scorecards/{timestamp}-{os-sha}.scores.json   raw scores (kept for re-analysis)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TASKS=""                       # empty => auto-discover (minus print-date/_example)
LAYERS=""
MODELS="opus"
MAX_BUDGET="1.50"
SHAS=()
DO_BUILD=1
DRY_RUN=0
CLEAN_WS=0
JOBS=1
WS_ROOT=""
REPEAT=""
BUILD_ARGS=()
OS_DIR="${OS_DIR:-$HOME/os}"

while [ $# -gt 0 ]; do
    case "$1" in
        --tasks) TASKS="$2"; shift 2;;
        --layers) LAYERS="$2"; shift 2;;
        --os-sha) SHAS+=("$2"); shift 2;;
        --models) MODELS="$2"; shift 2;;
        --max-budget-usd) MAX_BUDGET="$2"; shift 2;;
        --no-build) DO_BUILD=0; shift;;
        --no-home-isolation) BUILD_ARGS+=(--no-home-isolation); shift;;
        --dry-run) DRY_RUN=1; shift;;
        --jobs) JOBS="$2"; shift 2;;
        --ws-root) WS_ROOT="$2"; shift 2;;
        --clean-ws) CLEAN_WS=1; shift;;
        --repeat) REPEAT="$2"; shift 2;;
        --keep-ws) shift;;     # no-op: workspaces are kept by default
        *) echo "run.sh: unknown arg: $1" >&2; exit 1;;
    esac
done

RUNS_DIR="$SCRIPT_DIR/runs"
CONFIGS_DIR="$SCRIPT_DIR/configs"
TASKS_DIR="$SCRIPT_DIR/tasks"
SCORECARDS_DIR="$SCRIPT_DIR/scorecards"

# --- Resolve the os SHA(s) actually under test ---
[ "${#SHAS[@]}" -eq 0 ] && SHAS=(HEAD)
RESOLVED=()
for sha in "${SHAS[@]}"; do
    r="$(git -C "$OS_DIR" rev-parse --short "$sha^{commit}" 2>/dev/null)" || {
        echo "run.sh: ERROR sha '$sha' is not in $OS_DIR history" >&2; exit 2; }
    RESOLVED+=("$r")
done
if [ "${#RESOLVED[@]}" -gt 2 ]; then echo "run.sh: ERROR at most two --os-sha (A/B)" >&2; exit 1; fi
if [ "${#RESOLVED[@]}" -eq 2 ] && [ "${RESOLVED[0]}" = "${RESOLVED[1]}" ]; then
    echo "run.sh: ERROR both --os-sha resolve to the same commit (${RESOLVED[0]}); an A/B needs two different commits" >&2; exit 1
fi
SHA_ARGS=()
for r in "${RESOLVED[@]}"; do SHA_ARGS+=(--os-sha "$r"); done
if [ "${#RESOLVED[@]}" -eq 2 ]; then
    [ -z "$LAYERS" ] && LAYERS="full"
    [ "$LAYERS" = "full" ] || { echo "run.sh: ERROR A/B mode compares full@A vs full@B; drop --layers" >&2; exit 1; }
    OS_SHA="${RESOLVED[0]}-vs-${RESOLVED[1]}"
    ORDER="full@${RESOLVED[0]},full@${RESOLVED[1]}"
else
    [ -z "$LAYERS" ] && LAYERS="bare,full"
    OS_SHA="${RESOLVED[0]}"
    ORDER="$LAYERS"
fi
TS="$(date -u +%Y%m%dT%H%M%SZ)"
STAMP="${TS}-${OS_SHA}"
# never overwrite an earlier scorecard or merge into an earlier archive (same-second reruns)
while [ -e "$SCORECARDS_DIR/${STAMP}.md" ] || [ -e "$SCORECARDS_DIR/${STAMP}.scores.json" ] || [ -e "$RUNS_DIR/archive/$TS" ]; do
    sleep 1
    TS="$(date -u +%Y%m%dT%H%M%SZ)"
    STAMP="${TS}-${OS_SHA}"
done
echo "run.sh: os SHA=$OS_SHA  layers=$LAYERS  models=$MODELS  max-budget-usd=$MAX_BUDGET${REPEAT:+  repeat=$REPEAT}  stamp=$STAMP"

# --- Auto-discover tasks if none given (exclude the print-date smoke test) ---
if [ -z "$TASKS" ]; then
    TASKS="$(python3 - "$TASKS_DIR" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).resolve().parent / "harness"))
from run_matrix import read_task_meta
tasks_dir = Path(sys.argv[1])
tasks, skipped = [], []
for prompt in tasks_dir.rglob("prompt.md"):
    rel = prompt.parent.relative_to(tasks_dir)
    if any(seg.startswith("_") for seg in rel.parts):
        continue
    if rel.as_posix() == "print-date":
        continue
    if not read_task_meta(prompt.parent)["default"]:
        skipped.append(rel.as_posix())
        continue
    tasks.append(rel.as_posix())
print(",".join(sorted(tasks)))
if skipped:
    print("run.sh: excluded (default: false; name in --tasks to run): " + ", ".join(sorted(skipped)), file=sys.stderr)
PY
)"
fi
echo "run.sh: tasks=$TASKS"

# --- 1. Build per-layer configs from a snapshot of ~/os (unless reusing) ---
if [ "$DO_BUILD" -eq 1 ]; then
    echo "run.sh: building configs..."
    for r in "${RESOLVED[@]}"; do
        bash "$SCRIPT_DIR/harness/build_configs.sh" --os-sha "$r" ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"}
    done
else
    echo "run.sh: --no-build: reusing existing $CONFIGS_DIR"
fi

MATRIX_ARGS=(--tasks "$TASKS" --layers "$LAYERS" --models "$MODELS" --max-budget-usd "$MAX_BUDGET"
    --jobs "$JOBS"
    "${SHA_ARGS[@]}" --config-dir "$CONFIGS_DIR" --tasks-dir "$TASKS_DIR" --runs-dir "$RUNS_DIR")
[ -n "$WS_ROOT" ] && MATRIX_ARGS+=(--ws-root "$WS_ROOT")
[ -n "$REPEAT" ] && MATRIX_ARGS+=(--repeat "$REPEAT")

if [ "$DRY_RUN" -eq 1 ]; then
    python3 "$SCRIPT_DIR/harness/run_matrix.py" "${MATRIX_ARGS[@]}" --dry-run
    echo "run.sh: dry run only (nothing invoked, scored, or written to runs/)"
    exit 0
fi

# --- Preflight (free dry run): refuse before anything is moved or spent ---
# Catches an unbuilt snapshot (--no-build after ~/os moved), unknown layers and draft tasks.
PRE_OUT="$(python3 "$SCRIPT_DIR/harness/run_matrix.py" "${MATRIX_ARGS[@]}" --dry-run 2>&1)" || {
    echo "$PRE_OUT" | tail -3 >&2
    echo "run.sh: ERROR preflight failed; nothing was run, moved or scored" >&2
    exit 2
}
PLANNED="$(echo "$PRE_OUT" | sed -n 's/^total runs: *\([0-9][0-9]*\).*/\1/p' | tail -1)"

mkdir -p "$RUNS_DIR" "$SCORECARDS_DIR"

# --- Archive (move, never delete) prior transcripts + workspaces so they are not scored ---
shopt -s nullglob
prior=("$RUNS_DIR"/*.json "$RUNS_DIR"/*.trace.jsonl "$RUNS_DIR"/*.ws)
shopt -u nullglob
if [ "${#prior[@]}" -gt 0 ]; then
    ARCHIVE="$RUNS_DIR/archive/$TS"
    mkdir -p "$ARCHIVE"
    mv "${prior[@]}" "$ARCHIVE/"
    echo "run.sh: moved ${#prior[@]} prior run artifacts -> $ARCHIVE"
fi

# --- 2. Run the matrix ---
echo "run.sh: running matrix (this spends real API budget)..."
FINAL_RC=0
MATRIX_RC=0
python3 "$SCRIPT_DIR/harness/run_matrix.py" "${MATRIX_ARGS[@]}" || MATRIX_RC=$?
if [ "$MATRIX_RC" -ne 0 ]; then
    echo "run.sh: WARNING run_matrix exited $MATRIX_RC (see above); scoring what ran, scorecard will carry an INCOMPLETE MATRIX banner"
    FINAL_RC=1
fi

shopt -s nullglob
produced=("$RUNS_DIR"/*.json)
shopt -u nullglob
if [ "${#produced[@]}" -eq 0 ]; then
    echo "run.sh: ERROR the matrix produced no transcripts; no scorecard written" >&2
    exit 1
fi

# --- 3. Score every transcript in runs/ ---
echo "run.sh: scoring..."
SCORES_JSON="$SCORECARDS_DIR/${STAMP}.scores.json"
# score.py exits non-zero for score_exception / workspace_missing but still writes the full
# scores file: keep going so the scorecard names the problem, and fail at the end.
SCORE_RC=0
python3 "$SCRIPT_DIR/harness/score.py" \
    --runs-dir "$RUNS_DIR" --tasks-dir "$TASKS_DIR" --os-sha "$OS_SHA" > "$SCORES_JSON" || SCORE_RC=$?
if [ "$SCORE_RC" -ne 0 ]; then
    echo "run.sh: WARNING score.py exited $SCORE_RC (score_exception / workspace_missing / no runs); rendering scorecard anyway" >&2
    FINAL_RC=1
fi

# --- 4. Render the scorecard ---
echo "run.sh: rendering scorecard..."
SCORECARD="$SCORECARDS_DIR/${STAMP}.md"
STATS_ARGS=(--scores-file "$SCORES_JSON" --layers "$ORDER" --matrix-exit "$MATRIX_RC")
[ -n "$PLANNED" ] && STATS_ARGS+=(--planned-runs "$PLANNED")
if ! python3 "$SCRIPT_DIR/harness/stats.py" "${STATS_ARGS[@]}" > "$SCORECARD"; then
    [ -s "$SCORECARD" ] || rm -f "$SCORECARD"
    [ -s "$SCORES_JSON" ] || rm -f "$SCORES_JSON"
    echo "run.sh: ERROR scorecard could not be rendered (see above)" >&2
    exit 1
fi

# --- 5. Optionally delete per-run workspaces (only now that the scorecard exists) ---
if [ "$CLEAN_WS" -eq 1 ] && [ -s "$SCORECARD" ]; then
    echo "run.sh: cleaning up this invocation's workspaces ..."
    python3 - "$RUNS_DIR" <<'PY'
import json, re, shutil, sys
from pathlib import Path
# runs/ holds only this invocation's transcripts (prior ones were archived above).
for f in Path(sys.argv[1]).glob("*.json"):
    try:
        ws = json.loads(f.read_text()).get("_meta", {}).get("workspace_dir", "")
    except ValueError:
        continue
    p = Path(ws) if ws else None
    if p and p.name == "w" and re.fullmatch(r"w-[0-9a-f]{10}", p.parent.name):
        shutil.rmtree(p.parent, ignore_errors=True)   # per-run dir: w/ + cfg/
    elif p and re.fullmatch(r"w-[0-9a-f]{10}|.*\.ws", p.name):
        shutil.rmtree(p, ignore_errors=True)          # older flat workspace
PY
fi

echo "run.sh: DONE"
echo "run.sh: scorecard -> $SCORECARD"
echo "run.sh: scores    -> $SCORES_JSON"
if [ "$FINAL_RC" -ne 0 ]; then
    echo "run.sh: FINISHED WITH PROBLEMS (run_matrix rc=$MATRIX_RC, score.py rc=$SCORE_RC); see the scorecard" >&2
fi
exit "$FINAL_RC"
