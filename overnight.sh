#!/bin/bash
set -uo pipefail

# overnight.sh: three eval stages back to back, unattended.
#   1. canaries   bare vs full, opus + sonnet   (does each layer load at all?)
#   2. verdict    all 5 layers, repeat 3, opus   (default task set, canaries excluded)
#   3. verdict    all 5 layers, repeat 3, sonnet
# Stage 1 must finish cleanly (auth and harness ok) or the script stops; a canary that
# FAILS is a result, not a stop. Scorecards land in scorecards/. Logs in overnight-logs/.
#
# Usage: ./overnight.sh            # real run (spends tokens)
#        ./overnight.sh --dry-run  # plans all stages, spends nothing

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
DRY=""; [ "${1:-}" = "--dry-run" ] && DRY="--dry-run"
LOGDIR="$SCRIPT_DIR/overnight-logs"; mkdir -p "$LOGDIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOGDIR/$STAMP.log"
DONE="$LOGDIR/ran-$(date +%Y%m%d)"

if [ -z "$DRY" ] && [ -e "$DONE" ]; then echo "overnight.sh: already ran today ($DONE); exiting" | tee -a "$LOG"; exit 0; fi

# Resolve the os commit once so every stage tests the same snapshot even if ~/os moves overnight.
SHA="$(git -C "${OS_DIR:-$HOME/os}" rev-parse --short HEAD)"
echo "overnight.sh: $(date) os=$SHA ${DRY:+(dry run)}" | tee -a "$LOG"

# General task set = same auto-discovery as run.sh, minus canaries (stage 1 owns those).
GENERAL="$(python3 - "$SCRIPT_DIR/tasks" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).resolve().parent / "harness"))
from run_matrix import read_task_meta
root = Path(sys.argv[1]); out = []
for p in root.rglob("prompt.md"):
    rel = p.parent.relative_to(root)
    if any(s.startswith("_") for s in rel.parts) or rel.parts[0] == "canary" or rel.as_posix() == "print-date":
        continue
    if read_task_meta(p.parent)["default"]:
        out.append(rel.as_posix())
print(",".join(sorted(out)))
PY
)"
CANARIES="$(ls -d tasks/canary/*/ | sed 's#tasks/##; s#/$##' | paste -sd, -)"
echo "canaries: $CANARIES" | tee -a "$LOG"
echo "general:  $GENERAL" | tee -a "$LOG"

stage() {  # name, then run.sh args
    local name="$1"; shift
    echo "=== stage $name start $(date)" | tee -a "$LOG"
    caffeinate -i -s ./run.sh "$@" $DRY --os-sha "$SHA" --jobs 4 >> "$LOG" 2>&1
    local rc=$?
    echo "=== stage $name rc=$rc $(date)" | tee -a "$LOG"
    return $rc
}

# Stage 1 builds the snapshot (reads the keychain token); later stages reuse it.
stage canary --tasks "$CANARIES" --layers bare,full --models opus,sonnet --max-budget-usd 0.50 || {
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
stage verdict-opus   --no-build --tasks "$GENERAL" --layers bare,claude-md,memory,skills,full --repeat 3 --models opus   --max-budget-usd 1.50 --judge; R2=$?
stage verdict-sonnet --no-build --tasks "$GENERAL" --layers bare,claude-md,memory,skills,full --repeat 3 --models sonnet --max-budget-usd 1.50 --judge; R3=$?

[ -z "$DRY" ] && touch "$DONE"
echo "overnight.sh: finished $(date) verdict-opus rc=$R2 verdict-sonnet rc=$R3" | tee -a "$LOG"
echo "scorecards:"; ls -t scorecards/*.md | head -3 | tee -a "$LOG"
exit $(( R2 || R3 ))
