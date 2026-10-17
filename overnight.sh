#!/bin/bash
set -uo pipefail

# overnight.sh: one night of the eval matrix, unattended, inside one Max-plan usage window.
# Three modes (MODE env var or --mode; launchd sets MODE in the plist):
#   skill-lift   round 4 night 1 — per-skill lift. canary -> skill-sonnet -> skill-opus (gated on wall time).
#                skill tasks = default tasks whose meta has a `trigger:` and a real curated_skill, x layers
#                bare,skills,skills~trigger,skills~forced x high x r1, judged. A blind deck (--preset skill-lift)
#                is built after each stage, before run.sh archives that stage's runs.
#   skill-opus   the deferred skill-opus stage on its own night: canary -> skill-opus (no gate) -> deck.
#   orchestrate  round 4 night 3 — canary -> orch-a (dev-team/dev-team-auto forced, sonnet+opus)
#                -> orch-b (/fable-orchestrate forced, claude-fable-5-1). Multi-turn tasks run serially.
#   round3       the round-3 five-stage ladder (canary, verdict-sonnet, verdict-opus, c1, puzzles), unchanged.
# Stage canary must finish cleanly (auth and harness ok) or the script stops; a canary that FAILS is a result,
# not a stop. A stage that stopped on the usage limit (skipped stubs in runs/) ends the night; resume with
# `./run.sh --resume <same args>` once the window resets. Scorecards land in scorecards/ (one per stage).
# Logs in overnight-logs/. Per-task caps come from meta.yaml (no --max-budget-usd on verdict stages).
# Wall gate (skill-lift): skill-opus runs only if elapsed-so-far + its dry-run `est wall` <= WALL_CAP_SEC
# (default 16200 = 4.5 h); otherwise the log prints the deferred command (same as MODE=skill-opus).
# Opus stages run with CLAUDE_CODE_MAX_OUTPUT_TOKENS=$OPUS_MAX_OUTPUT_TOKENS (default 32000): round 3 showed
# opus/high under `--tools ""` writing fake tool-call XML for one 128k-token turn (~$2.65, and --max-budget-usd
# only checks between turns). 32k tokens is far above any real answer here and caps that failure at ~$0.65.
# Set OPUS_MAX_OUTPUT_TOKENS= (empty) to lift it.
#
# Usage: MODE=skill-lift ./overnight.sh            # real run (spends tokens)
#        MODE=skill-lift ./overnight.sh --dry-run  # plans all stages (FITS/OVER + est wall per stage), spends nothing
#        ./overnight.sh --mode skill-opus|orchestrate [--dry-run]
# Point launchd at a night: ./schedule-overnight.sh 2026-10-17 skill-lift

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
MODE="${MODE:-skill-lift}"; DRY=""
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY="--dry-run"; shift;;
        --mode) MODE="$2"; shift 2;;
        --mode=*) MODE="${1#--mode=}"; shift;;
        *) echo "overnight.sh: unknown arg $1" >&2; exit 2;;
    esac
done
case "$MODE" in skill-lift|skill-opus|orchestrate|round3) ;; *) echo "overnight.sh: unknown MODE '$MODE' (skill-lift|skill-opus|orchestrate|round3)" >&2; exit 2;; esac
LOGDIR="$SCRIPT_DIR/overnight-logs"; mkdir -p "$LOGDIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOGDIR/$STAMP-$MODE.log"
DONE="$LOGDIR/ran-$(date +%Y%m%d)-$MODE"
T0="$(date +%s)"
WALL_CAP_SEC="${WALL_CAP_SEC:-16200}"
OPUS_MAX_OUTPUT_TOKENS="${OPUS_MAX_OUTPUT_TOKENS-32000}"
# Usage-window shares (nominal $) for the dry-run FITS verdicts; the night's total must stay <= 100.
WIN_SONNET=40; WIN_OPUS=40; WIN_C1=8; WIN_PUZZLES=12; WIN_ORCH=40

if [ -z "$DRY" ] && [ -e "$DONE" ]; then echo "overnight.sh: already ran today ($DONE); exiting" | tee -a "$LOG"; exit 0; fi

# Resolve the os commit once so every stage tests the same snapshot even if ~/os moves overnight.
SHA="$(git -C "${OS_DIR:-$HOME/os}" rev-parse --short HEAD)"
echo "overnight.sh: $(date) mode=$MODE os=$SHA ${DRY:+(dry run)}" | tee -a "$LOG"

# Task sets. GENERAL = default set minus canaries, puzzles and the XL orchestration task (own stages).
# OPUS = GENERAL tasks that discriminated between layers in the stamped history, plus every task with no
# history yet (new this round); non-discriminating known tasks skip the Opus arm to fit the window.
# SKILL = default tasks with a `trigger:` phrase and a real curated_skill (the round-4 skill-lift set).
eval "$(python3 - "$SCRIPT_DIR/tasks" "$SCRIPT_DIR/scorecards" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).resolve().parent / "harness"))
from run_matrix import read_task_meta, history_discriminating, load_history
root = Path(sys.argv[1]); general, puzzles, skill = [], [], []
for p in root.rglob("prompt.md"):
    rel = p.parent.relative_to(root); name = rel.as_posix()
    if any(s.startswith("_") for s in rel.parts) or rel.parts[0] == "canary" or name == "print-date":
        continue
    meta = read_task_meta(p.parent)
    if not meta["default"]:
        continue
    if rel.parts[0] == "puzzles": puzzles.append(name)
    elif name != "process/orchestrate-two-part": general.append(name)
    cur = (meta.get("curated_skill") or "").split()[0] if (meta.get("curated_skill") or "").strip() else ""
    if meta.get("trigger") and cur and cur != "none":
        skill.append(name)
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
print(f"SKILL={','.join(sorted(skill))}")
PY
)"
CANARIES="$(ls -d tasks/canary/*/ | sed 's#tasks/##; s#/$##' | paste -sd, -)"
C1="process/orchestrate-two-part"
ORCH="coding/pathguard-resolver,coding/rangestats-engine"   # default: false tasks; curated dev-team / dev-team-auto
ARM_LAYERS="bare,skills,skills~trigger,skills~forced"
echo "canaries: $CANARIES" | tee -a "$LOG"
case "$MODE" in
    round3) echo "general:  $GENERAL" | tee -a "$LOG"; echo "opus arm: $OPUS" | tee -a "$LOG"; echo "puzzles:  $PUZZLES" | tee -a "$LOG";;
    skill-lift|skill-opus) echo "skill set: $SKILL" | tee -a "$LOG"
        [ -n "$SKILL" ] || { echo "overnight.sh: no default task has trigger + curated_skill; nothing to measure" | tee -a "$LOG"; exit 1; };;
    orchestrate) echo "orchestrate: $ORCH" | tee -a "$LOG";;
esac

stage() {  # name, then run.sh args. A stage whose --models is exactly `opus` gets the output-token cap.
    local name="$1"; shift
    local cap=()
    [ -n "$OPUS_MAX_OUTPUT_TOKENS" ] && [[ " $* " == *" --models opus "* ]] && cap=(env "CLAUDE_CODE_MAX_OUTPUT_TOKENS=$OPUS_MAX_OUTPUT_TOKENS")
    echo "=== stage $name start $(date)${cap:+ (CLAUDE_CODE_MAX_OUTPUT_TOKENS=$OPUS_MAX_OUTPUT_TOKENS)}" | tee -a "$LOG"
    caffeinate -i -s ${cap[@]+"${cap[@]}"} ./run.sh "$@" $DRY --os-sha "$SHA" --jobs 4 >> "$LOG" 2>&1
    local rc=$?
    echo "=== stage $name rc=$rc $(date)" | tee -a "$LOG"
    [ -n "$DRY" ] && { grep -E 'verdict: (FITS|OVER)' "$LOG" | tail -1 | sed "s/^/    $name /"; grep -E '^est wall:' "$LOG" | tail -1 | sed "s/^/    $name /"; }
    return $rc
}

# Dry-run wall estimate (seconds) for a stage's run.sh args; 0 when run_matrix printed no `est wall:` line.
est_secs() {
    ./run.sh "$@" --dry-run --os-sha "$SHA" --jobs 4 2>&1 | grep -E '^est wall:' | tail -1 \
        | sed -E 's/.*est wall: ([0-9]+)h ([0-9]+)m.*/\1 \2/' | awk 'NF==2 {print $1*3600+$2*60; f=1} END {if (!f) print 0}'
}
hm() { printf '%dh %02dm' $(( $1 / 3600 )) $(( ($1 % 3600) / 60 )); }

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

# Blind deck from the stage that just finished: must run before the next run.sh archives runs/ (deck.py drops
# runs whose workspace is gone, and reads run jsons from runs/). rc 1 = no pairs (an empty round is not an error
# for the night). Dry runs write no scores, so they skip it.
deck_after() {  # stage name
    [ -n "$DRY" ] && return 0
    local scores; scores="$(ls -t scorecards/*.scores.json 2>/dev/null | head -1)"
    [ -n "$scores" ] || { echo "deck ($1): no scores file; skipped" | tee -a "$LOG"; return 0; }
    python3 harness/deck.py build --preset skill-lift --scores-file "$scores" >> "$LOG" 2>&1 \
        && echo "deck ($1): round built from $(basename "$scores")" | tee -a "$LOG" \
        || echo "deck ($1): no round built (rc=$?, see log)" | tee -a "$LOG"
}

# Stage 1 builds the snapshot (reads the keychain token); later stages reuse it.
case "$MODE" in
    round3)      CAN=(--tasks "$CANARIES" --layers bare,full --models opus,sonnet);;
    skill-lift)  CAN=(--tasks "$CANARIES" --layers bare,skills --models sonnet);;
    skill-opus)  CAN=(--tasks canary/skill --layers bare,skills --models opus);;
    orchestrate) CAN=(--tasks canary/skill --layers skills --models sonnet);;
esac
stage canary "${CAN[@]}" --effort high --max-budget-usd 0.50 || {
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

finish() {  # summary line, then rc
    [ -z "$DRY" ] && touch "$DONE"
    echo "overnight.sh: finished $(date) mode=$MODE $1" | tee -a "$LOG"
    echo "scorecards:"; ls -t scorecards/*.md | head -5 | tee -a "$LOG"
    exit "$2"
}

case "$MODE" in
round3)
    S_SONNET=(--no-build --effort high --tasks "$GENERAL" --layers "bare,claude-md,memory,memory~nohook,skills,full" --models sonnet --repeat 1 --judge --window-usd "$WIN_SONNET")
    stage verdict-sonnet "${S_SONNET[@]}"; R2=$?; window_exhausted verdict-sonnet "${S_SONNET[*]} --jobs 4"
    S_OPUS=(--no-build --effort high --tasks "$OPUS" --layers "bare,claude-md,memory,memory~nohook,skills,full" --models opus --repeat 1 --judge --window-usd "$WIN_OPUS")
    stage verdict-opus "${S_OPUS[@]}"; R3=$?; window_exhausted verdict-opus "${S_OPUS[*]} --jobs 4"
    S_C1=(--no-build --effort high --tasks "$C1" --layers bare,claude-md,full --models sonnet --repeat 1 --judge --window-usd "$WIN_C1")
    stage c1 "${S_C1[@]}"; R4=$?; window_exhausted c1 "${S_C1[*]} --jobs 4"
    S_PUZ=(--no-build --effort low,medium,high --tasks "$PUZZLES" --layers bare --models haiku,sonnet,opus --repeat 3 --window-usd "$WIN_PUZZLES")
    stage puzzles "${S_PUZ[@]}"; R5=$?; window_exhausted puzzles "${S_PUZ[*]} --jobs 4"
    finish "verdict-sonnet rc=$R2 verdict-opus rc=$R3 c1 rc=$R4 puzzles rc=$R5" $(( R2 || R3 || R4 || R5 ))
    ;;
skill-lift)
    S_SK_SONNET=(--no-build --effort high --tasks "$SKILL" --layers "$ARM_LAYERS" --models sonnet --repeat 1 --judge --window-usd "$WIN_SONNET")
    S_SK_OPUS=(--no-build --effort high --tasks "$SKILL" --layers "$ARM_LAYERS" --models opus --repeat 1 --judge --window-usd "$WIN_OPUS")
    stage skill-sonnet "${S_SK_SONNET[@]}"; R2=$?; window_exhausted skill-sonnet "${S_SK_SONNET[*]} --jobs 4"
    deck_after skill-sonnet
    # Wall gate: opus runs only if what is left of the night fits its estimate. A dry run has no elapsed time,
    # so it gates on sonnet-est + opus-est instead (the planning answer for the night).
    EST_OPUS="$(est_secs "${S_SK_OPUS[@]}")"
    if [ -n "$DRY" ]; then USED="$(est_secs "${S_SK_SONNET[@]}")"; else USED=$(( $(date +%s) - T0 )); fi
    if (( USED + EST_OPUS <= WALL_CAP_SEC )); then
        echo "wall gate: used $(hm "$USED") + skill-opus est $(hm "$EST_OPUS") <= cap $(hm "$WALL_CAP_SEC"); running skill-opus" | tee -a "$LOG"
        stage skill-opus "${S_SK_OPUS[@]}"; R3=$?; window_exhausted skill-opus "${S_SK_OPUS[*]} --jobs 4"
        deck_after skill-opus
    else
        echo "wall gate: used $(hm "$USED") + skill-opus est $(hm "$EST_OPUS") > cap $(hm "$WALL_CAP_SEC"); skill-opus deferred. Schedule it for another night:" | tee -a "$LOG"
        echo "    cd $SCRIPT_DIR && ./schedule-overnight.sh <YYYY-MM-DD> skill-opus" | tee -a "$LOG"
        R3=0
    fi
    finish "skill-sonnet rc=$R2 skill-opus rc=$R3 (deferred=$(( USED + EST_OPUS > WALL_CAP_SEC )))" $(( R2 || R3 ))
    ;;
skill-opus)
    S_SK_OPUS=(--no-build --effort high --tasks "$SKILL" --layers "$ARM_LAYERS" --models opus --repeat 1 --judge --window-usd "$WIN_OPUS")
    stage skill-opus "${S_SK_OPUS[@]}"; R2=$?; window_exhausted skill-opus "${S_SK_OPUS[*]} --jobs 4"
    deck_after skill-opus
    finish "skill-opus rc=$R2" "$R2"
    ;;
orchestrate)
    S_ORCH_A=(--no-build --effort high --tasks "$ORCH" --layers skills,skills~forced --models sonnet,opus --repeat 1 --judge --window-usd "$WIN_ORCH")
    stage orch-a "${S_ORCH_A[@]}"; R2=$?; window_exhausted orch-a "${S_ORCH_A[*]} --jobs 4"
    S_ORCH_B=(--no-build --effort high --tasks "$ORCH" --layers skills,skills~forced.fable-orchestrate --models claude-fable-5-1 --repeat 1 --judge --window-usd "$WIN_ORCH")
    stage orch-b "${S_ORCH_B[@]}"; R3=$?; window_exhausted orch-b "${S_ORCH_B[*]} --jobs 4"
    finish "orch-a rc=$R2 orch-b rc=$R3" $(( R2 || R3 ))
    ;;
esac
