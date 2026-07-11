#!/bin/bash
set -euo pipefail

# run.sh — top-level orchestrator for one iteration of the eval matrix.
#
# Stamps the ~/os git SHA, (re)builds the per-rung configs, runs the task×rung×model
# matrix against frozen workspaces, scores every run, renders a markdown scorecard, and
# cleans up the per-run workspaces.
#
# Usage:
#   ./run.sh                       # full matrix: 12 tasks × rungs 1-4 on Sonnet
#   ./run.sh --tasks a,b --rungs 1,4 --models claude-sonnet-4-6
#   ./run.sh --opus-spotcheck      # ALSO run rungs 1,4 on Opus (bare-vs-full spot check)
#   ./run.sh --no-build            # skip build_configs.sh (reuse existing configs/)
#   ./run.sh --keep-ws             # keep runs/*.ws (default: cleaned after scoring)
#
# Outputs:
#   scorecards/{timestamp}-{os-sha}.md   the scorecard
#   scorecards/{timestamp}-{os-sha}.scores.json   raw scores (kept for re-analysis)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TASKS=""                       # empty => auto-discover (minus print-date/_example)
RUNGS="1,2,3,4"
MODELS="claude-sonnet-4-6"
OPUS_MODEL="claude-opus-4-8"
DO_BUILD=1
KEEP_WS=0
OPUS_SPOTCHECK=0
OS_DIR="${OS_DIR:-$HOME/os}"

while [ $# -gt 0 ]; do
    case "$1" in
        --tasks) TASKS="$2"; shift 2;;
        --rungs) RUNGS="$2"; shift 2;;
        --models) MODELS="$2"; shift 2;;
        --no-build) DO_BUILD=0; shift;;
        --keep-ws) KEEP_WS=1; shift;;
        --opus-spotcheck) OPUS_SPOTCHECK=1; shift;;
        *) echo "run.sh: unknown arg: $1" >&2; exit 1;;
    esac
done

RUNS_DIR="$SCRIPT_DIR/runs"
CONFIGS_DIR="$SCRIPT_DIR/configs"
TASKS_DIR="$SCRIPT_DIR/tasks"
SCORECARDS_DIR="$SCRIPT_DIR/scorecards"
mkdir -p "$RUNS_DIR" "$SCORECARDS_DIR"

# --- Stamp the ~/os git SHA (which version of the setup is under test) ---
if [ -d "$OS_DIR/.git" ]; then
    OS_SHA="$(git -C "$OS_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
else
    OS_SHA="unknown"
fi
TS="$(date -u +%Y%m%dT%H%M%SZ)"
STAMP="${TS}-${OS_SHA}"
echo "run.sh: os SHA=$OS_SHA  stamp=$STAMP"

# --- Auto-discover tasks if none given (exclude the print-date smoke test) ---
if [ -z "$TASKS" ]; then
    TASKS="$(python3 - "$TASKS_DIR" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "harness"))
tasks_dir = Path(sys.argv[1])
tasks = []
for prompt in tasks_dir.rglob("prompt.md"):
    rel = prompt.parent.relative_to(tasks_dir)
    if any(seg.startswith("_") for seg in rel.parts):
        continue
    if rel.as_posix() == "print-date":
        continue
    tasks.append(rel.as_posix())
print(",".join(sorted(tasks)))
PY
)"
fi
echo "run.sh: tasks=$TASKS"
echo "run.sh: rungs=$RUNGS  models=$MODELS  opus_spotcheck=$OPUS_SPOTCHECK"

# --- 1. Build per-rung configs from ~/.claude (unless reusing) ---
if [ "$DO_BUILD" -eq 1 ]; then
    echo "run.sh: building configs..."
    bash "$SCRIPT_DIR/harness/build_configs.sh"
else
    echo "run.sh: --no-build: reusing existing $CONFIGS_DIR"
fi

# --- 2. Run the matrix (Sonnet ladder) ---
echo "run.sh: running matrix (this spends real API budget)..."
python3 "$SCRIPT_DIR/harness/run_matrix.py" \
    --tasks "$TASKS" --rungs "$RUNGS" --models "$MODELS" \
    --config-dir "$CONFIGS_DIR" --tasks-dir "$TASKS_DIR" --runs-dir "$RUNS_DIR" || \
    echo "run.sh: WARNING run_matrix reported failures (see above); continuing to score what ran"

# --- 2b. Optional Opus bare-vs-full spot check (rungs 1 & 4 only) ---
if [ "$OPUS_SPOTCHECK" -eq 1 ]; then
    echo "run.sh: Opus spot check (rungs 1,4 on $OPUS_MODEL)..."
    python3 "$SCRIPT_DIR/harness/run_matrix.py" \
        --tasks "$TASKS" --rungs "1,4" --models "$OPUS_MODEL" \
        --config-dir "$CONFIGS_DIR" --tasks-dir "$TASKS_DIR" --runs-dir "$RUNS_DIR" || \
        echo "run.sh: WARNING Opus spot check reported failures; continuing"
fi

# --- 3. Score every transcript in runs/ ---
echo "run.sh: scoring..."
SCORES_JSON="$SCORECARDS_DIR/${STAMP}.scores.json"
python3 "$SCRIPT_DIR/harness/score.py" \
    --runs-dir "$RUNS_DIR" --tasks-dir "$TASKS_DIR" --os-sha "$OS_SHA" > "$SCORES_JSON"

# --- 4. Render the scorecard ---
echo "run.sh: rendering scorecard..."
SCORECARD="$SCORECARDS_DIR/${STAMP}.md"
python3 "$SCRIPT_DIR/harness/stats.py" --scores-file "$SCORES_JSON" > "$SCORECARD"

# --- 5. Clean up per-run workspaces (they can be large: node_modules, venvs) ---
if [ "$KEEP_WS" -eq 0 ]; then
    echo "run.sh: cleaning up runs/*.ws ..."
    rm -rf "$RUNS_DIR"/*.ws 2>/dev/null || true
fi

echo "run.sh: DONE"
echo "run.sh: scorecard -> $SCORECARD"
echo "run.sh: scores    -> $SCORES_JSON"