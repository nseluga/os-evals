#!/bin/bash
set -uo pipefail

# overnight.sh: the round-3 matrix in five stages, unattended, inside one Max-plan usage window.
#   1. canary          canaries x bare,full x opus+sonnet            (does each layer load at all? builds the snapshot)
#   2. verdict-sonnet  general set x 6 layers (incl. memory~nohook) x sonnet x high x r1, judged
#   3. verdict-opus    discriminating + new tasks x 6 layers x opus x high x r1, judged
#   4. c1              process/orchestrate-two-part x bare,claude-md,full x sonnet (XL, cap from meta)
#   5. puzzles         puzzles/* (layer_neutral -> bare) x haiku,sonnet,opus x low,medium,high x r3 (frontier only)
# Stage 1 must finish cleanly (auth and harness ok) or the script stops; a canary that FAILS is a result,
# not a stop. A stage that stopped on the usage limit (skipped stubs in runs/) ends the night; resume with
# `./run.sh --resume <same args>` once the window resets. Scorecards land in scorecards/ (one per stage).
# Logs in overnight-logs/. Per-task caps come from meta.yaml (no --max-budget-usd on verdict stages).
#
# Usage: ./overnight.sh            # real run (spends tokens)
#        ./overnight.sh --dry-run  # plans all stages (FITS/OVER per stage), spends nothing

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
DRY=""; [ "${1:-}" = "--dry-run" ] && DRY="--dry-run"
LOGDIR="$SCRIPT_DIR/overnight-logs"; mkdir -p "$LOGDIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOGDIR/$STAMP.log"
DONE="$LOGDIR/ran-$(date +%Y%m%d)"
LAYERS="bare,claude-md,memory,memory~nohook,skills,full"
# Usage-window shares (nominal $) for the dry-run FITS verdicts; the night's total must stay <= 100.
WIN_SONNET=40; WIN_OPUS=40; WIN_C1=8; WIN_PUZZLES=12

if [ -z "$DRY" ] && [ -e "$DONE" ]; then echo "overnight.sh: already ran today ($DONE); exiting" | tee -a "$LOG"; exit 0; fi

# Resolve the os commit once so every stage tests the same snapshot even if ~/os moves overnight.
SHA="$(git -C "${OS_DIR:-$HOME/os}" rev-parse --short HEAD)"
echo "overnight.sh: $(date) os=$SHA ${DRY:+(dry run)}" | tee -a "$LOG"

# Task sets. GENERAL = default set minus canaries, puzzles and the XL orchestration task (own stages).
# OPUS = GENERAL tasks that discriminated between layers in the stamped history, plus every task with no
# history yet (new this round); non-discriminating known tasks skip the Opus arm to fit the window.
eval "$(python3 - "$SCRIPT_DIR/tasks" "$SCRIPT_DIR/scorecards" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).resolve().parent / "harness"))
from run_matrix import read_task_meta, history_discriminating, load_history
root = Path(sys.argv[1]); general, puzzles = [], []
for p in root.rglob("prompt.md"):
    rel = p.parent.relative_to(root); name = rel.as_posix()
    if any(s.startswith("_") for s in rel.parts) or rel.parts[0] == "canary" or name == "print-date":
        continue
    if not read_task_meta(p.parent)["default"]:
        continue
    if rel.parts[0] == "puzzles": puzzles.append(name)
    elif name != "process/orchestrate-two-part": general.append(name)
# Round-3 tasks (2026-10-15) always take the Opus arm on their first nights: smoke runs gave some of them
# two-layer history that says "not discriminating" on one sonnet/low pair, which proves nothing.
NEW_R3 = {"coding/bcns-connector-crewlog", "coding/bcns-tenant-leak", "process/gh-merge-live", "process/inline-one-fix",
          "writing/client-email-fee", "writing/lane-repair", "writing/quote-deluxe-notes"}
disc = {t for t, _fam in history_discriminating(Path(sys.argv[2]))}
seen = {r["task"] for recs in load_history(Path(sys.argv[2])) for r in recs if r.get("task")}
opus = [t for t in general if t in disc or t not in seen or t in NEW_R3]
print(f"GENERAL={','.join(sorted(general))}")
print(f"OPUS={','.join(sorted(opus))}")
print(f"PUZZLES={','.join(sorted(puzzles))}")
PY
)"
CANARIES="$(ls -d tasks/canary/*/ | sed 's#tasks/##; s#/$##' | paste -sd, -)"
C1="process/orchestrate-two-part"
echo "canaries: $CANARIES" | tee -a "$LOG"
echo "general:  $GENERAL" | tee -a "$LOG"
echo "opus arm: $OPUS" | tee -a "$LOG"
echo "puzzles:  $PUZZLES" | tee -a "$LOG"

stage() {  # name, then run.sh args
    local name="$1"; shift
    echo "=== stage $name start $(date)" | tee -a "$LOG"
    caffeinate -i -s ./run.sh "$@" $DRY --os-sha "$SHA" --jobs 4 >> "$LOG" 2>&1
    local rc=$?
    echo "=== stage $name rc=$rc $(date)" | tee -a "$LOG"
    [ -n "$DRY" ] && grep -E 'verdict: (FITS|OVER)' "$LOG" | tail -1 | sed "s/^/    $name /"
    return $rc
}

# The usage window is gone when run_matrix wrote `skipped` stubs (2 consecutive usage-limit runs).
window_exhausted() {  # name of the stage that just ran
    [ -n "$DRY" ] && return 1
    python3 - "$SCRIPT_DIR/runs" <<'PY' && return 1
import json, sys
from pathlib import Path
for f in Path(sys.argv[1]).glob("*.json"):
    try: m = json.loads(f.read_text()).get("_meta", {})
    except ValueError: continue
    if m.get("skipped"): sys.exit(1)
PY
    echo "overnight.sh: stage $1 stopped on the usage limit; ending the night. After the window resets:" | tee -a "$LOG"
    echo "    cd $SCRIPT_DIR && ./run.sh --resume $2" | tee -a "$LOG"
    [ -z "$DRY" ] && touch "$DONE"; exit 1
}

# Stage 1 builds the snapshot (reads the keychain token); later stages reuse it.
stage canary --tasks "$CANARIES" --layers bare,full --models opus,sonnet --effort high --max-budget-usd 0.50 || {
    echo "overnight.sh: canary stage exited non-zero; stopping (check the log for auth or harness problems)" | tee -a "$LOG"
    [ -z "$DRY" ] && touch "$DONE"; exit 1; }
# Fail fast: if the canary runs all died as infra (auth, rate limit, no result), the token or CLI is
# broken and the general stages would only burn hours. Dry runs write no transcripts and skip this.
if [ -z "$DRY" ]; then
    python3 - "$SCRIPT_DIR/runs" <<'PY' || { echo "overnight.sh: every canary run was an infra failure (auth or CLI); stopping before the general stages" | tee -a "$LOG"; touch "$DONE"; exit 1; }
import json, sys
from pathlib import Path
n = bad = 0
for f in Path(sys.argv[1]).glob("*.json"):
    try: m = json.loads(f.read_text()).get("_meta", {})
    except ValueError: continue
    n += 1
    bad += bool(m.get("auth_error") or m.get("rate_limited") or m.get("no_result"))
print(f"canary transcripts={n} infra-flagged={bad}")
sys.exit(1 if n == 0 or bad == n else 0)
PY
fi

S_SONNET=(--no-build --effort high --tasks "$GENERAL" --layers "$LAYERS" --models sonnet --repeat 1 --judge --window-usd "$WIN_SONNET")
stage verdict-sonnet "${S_SONNET[@]}"; R2=$?; window_exhausted verdict-sonnet "${S_SONNET[*]} --jobs 4"
S_OPUS=(--no-build --effort high --tasks "$OPUS" --layers "$LAYERS" --models opus --repeat 1 --judge --window-usd "$WIN_OPUS")
stage verdict-opus "${S_OPUS[@]}"; R3=$?; window_exhausted verdict-opus "${S_OPUS[*]} --jobs 4"
S_C1=(--no-build --effort high --tasks "$C1" --layers bare,claude-md,full --models sonnet --repeat 1 --judge --window-usd "$WIN_C1")
stage c1 "${S_C1[@]}"; R4=$?; window_exhausted c1 "${S_C1[*]} --jobs 4"
S_PUZ=(--no-build --effort low,medium,high --tasks "$PUZZLES" --layers bare --models haiku,sonnet,opus --repeat 3 --window-usd "$WIN_PUZZLES")
stage puzzles "${S_PUZ[@]}"; R5=$?; window_exhausted puzzles "${S_PUZ[*]} --jobs 4"

[ -z "$DRY" ] && touch "$DONE"
echo "overnight.sh: finished $(date) verdict-sonnet rc=$R2 verdict-opus rc=$R3 c1 rc=$R4 puzzles rc=$R5" | tee -a "$LOG"
echo "scorecards:"; ls -t scorecards/*.md | head -5 | tee -a "$LOG"
exit $(( R2 || R3 || R4 || R5 ))
