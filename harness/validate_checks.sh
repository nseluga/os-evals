#!/bin/bash
# harness/validate_checks.sh — free (no model calls) two-sided validation of every live task's check.sh.
#   good workspace/transcript -> exit 0; bad -> exit 1;
#   workspace checks only: WORKSPACE_DIR unset -> 2, WORKSPACE_DIR nonexistent -> 2.
#   Text-only checks (never mention WORKSPACE_DIR) have no exit-2 path: unset/missing print N/A.
# Usage: harness/validate_checks.sh [--task cat/name] [--keep]
#   Drafts (_draft/...) are skipped unless named explicitly: --task _draft/knowledge/<name>
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASKS="$ROOT/tasks"
TMP="${VALIDATE_TMP:-${TMPDIR:-/tmp}/os-evals-validate}"
CACHE="$TMP/_cache"
ONLY=""; KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in --task) ONLY="$2"; shift 2;; --keep) KEEP=1; shift;;
  *) echo "unknown arg $1" >&2; exit 64;; esac
done
mkdir -p "$TMP" "$CACHE"

ref_field() { # $1=ref file $2=key -> value (comment stripped)
  sed -n "s/^[[:space:]]*$2:[[:space:]]*\([^# ]*\).*/\1/p" "$1" | head -1; }

restore() { # $1=origin $2=ref $3=dest
  local sha; sha="$(git -C "$1" rev-parse "$2")" || return 1
  mkdir -p "$3"; git -C "$1" archive --format=tar "$sha" | tar -x -C "$3"; }

provision() { # $1=task_dir $2=dest $3=task-name ; setup.sh with cache of node_modules/.venv
  local setup="$1/setup.sh" dest="$2" key heavy
  [ -f "$setup" ] || return 0
  if [ -f "$dest/package-lock.json" ]; then heavy=node_modules; key="npm-$(shasum -a 256 "$dest/package-lock.json" | cut -d' ' -f1)"
  else heavy=.venv; key="venv-${3//\//-}"; fi
  if [ -d "$CACHE/$key/$heavy" ]; then cp -R "$CACHE/$key/$heavy" "$dest/$heavy"; return 0; fi
  (cd "$dest" && bash "$setup") >"$dest/.setup.log" 2>&1 || { echo "setup.sh failed, see $dest/.setup.log" >&2; return 1; }
  [ -d "$dest/$heavy" ] && { mkdir -p "$CACHE/$key"; cp -R "$dest/$heavy" "$CACHE/$key/$heavy"; }
  return 0; }

RC=""; OUT=""
run_check() { # $1=check.sh $2=stdin file $3=WORKSPACE_DIR value or "-" for unset
  local c="$1" in="$2" ws="$3"
  if [ "$ws" = "-" ]; then OUT="$(env -u WORKSPACE_DIR "$c" <"$in" 2>&1)"; RC=$?
  else OUT="$(WORKSPACE_DIR="$ws" "$c" <"$in" 2>&1)"; RC=$?; fi
  OUT="$(printf '%s' "$OUT" | tail -3 | tr '\n' ' ')"; }

tasks=()
while IFS= read -r m; do
  t="${m#$TASKS/}"; t="${t%/meta.yaml}"
  skip=0; IFS=/ read -ra p <<<"$t"; for s in "${p[@]}"; do case "$s" in _*) skip=1;; esac; done
  [ "$skip" = 1 ] && [ "$t" != "$ONLY" ] && continue; [ "$t" = print-date ] && continue
  [ -n "$ONLY" ] && [ "$t" != "$ONLY" ] && continue
  tasks+=("$t")
done < <(find "$TASKS" -name meta.yaml | sort)
[ ${#tasks[@]} -eq 0 ] && { echo "no tasks matched" >&2; exit 64; }

printf '%-42s %-5s %-5s %-6s %-8s %s\n' task good bad unset missing verdict
mism=0; mismsg=""
for t in "${tasks[@]}"; do
  td="$TASKS/$t"; chk="$td/check.sh"; w="$TMP/${t//\//__}"; rm -rf "$w"; mkdir -p "$w"
  textonly=0; grep -q WORKSPACE_DIR "$chk" || textonly=1
  # meta.yaml anchor_only at column 0 => UNVALIDATED by design
  if grep -q '^anchor_only:[[:space:]]*true' "$td/meta.yaml"; then
    printf '%-42s %-5s %-5s %-6s %-8s %s\n' "$t" - - - - UNVALIDATED; continue; fi
  ref="$td/workspace.ref"; sol=""; origin=""
  [ -f "$ref" ] && { sol="$(ref_field "$ref" solution_sha)"; origin="$(ref_field "$ref" origin)"; base="$(ref_field "$ref" sha)"; }
  g=""; b=""; gin=/dev/null; bin=/dev/null; err=""
  if [ -n "$sol" ] && [ -n "$origin" ]; then
    restore "$origin" "$sol" "$w/good" && restore "$origin" "$base" "$w/bad" || err="restore failed"
    [ -z "$err" ] && { provision "$td" "$w/good" "$t" && provision "$td" "$w/bad" "$t" || err="setup failed"; }
    g="$w/good"; b="$w/bad"
  elif [ -d "$td/tests/good" ] && [ -d "$td/tests/bad" ]; then
    if [ "$textonly" = 1 ]; then
      gin="$td/tests/good/transcript.json"; bin="$td/tests/bad/transcript.json"; g="$w/good"; b="$w/bad"; mkdir -p "$g" "$b"
    else
      cp -R "$td/tests/good" "$w/good"; cp -R "$td/tests/bad" "$w/bad"; g="$w/good"; b="$w/bad"
      echo '{"result":""}' >"$w/empty.json"; gin="$w/empty.json"; bin="$gin"
    fi
  else
    printf '%-42s %-5s %-5s %-6s %-8s %s\n' "$t" - - - - UNVALIDATED; continue
  fi
  [ -n "$err" ] && { printf '%-42s %s\n' "$t" "MISMATCH ($err)"; mism=1; continue; }
  # workspace checks with solution_sha get empty stdin JSON too
  [ "$gin" = /dev/null ] && { echo '{"result":""}' >"$w/empty.json"; gin="$w/empty.json"; bin="$gin"; }
  if [ "$textonly" = 1 ]; then ws_g="-"; ws_b="-"; else ws_g="$g"; ws_b="$b"; fi
  run_check "$chk" "$gin" "$ws_g"; rg=$RC; og="$OUT"
  run_check "$chk" "$bin" "$ws_b"; rb=$RC; ob="$OUT"
  if [ "$textonly" = 1 ]; then ru="N/A"; rm_="N/A"; else
    run_check "$chk" "$gin" "-"; ru=$RC; ou="$OUT"
    run_check "$chk" "$gin" "$w/does-not-exist"; rm_=$RC; om="$OUT"; fi
  v=OK; why=""
  [ "$rg" != 0 ] && { v=MISMATCH; why+=" good rc=$rg: $og;"; }
  [ "$rb" != 1 ] && { v=MISMATCH; why+=" bad rc=$rb: $ob;"; }
  [ "$textonly" = 0 ] && [ "$ru" != 2 ] && { v=MISMATCH; why+=" unset rc=$ru: ${ou:-};"; }
  [ "$textonly" = 0 ] && [ "$rm_" != 2 ] && { v=MISMATCH; why+=" missing rc=$rm_: ${om:-};"; }
  # extra text-only fixtures (good2.., bad2..: usually real stored answers) must agree too
  if [ "$textonly" = 1 ]; then
    for f in "$td"/tests/good?*/transcript.json "$td"/tests/bad?*/transcript.json; do
      [ -f "$f" ] || continue
      fx="$(basename "$(dirname "$f")")"; want=0; case "$fx" in bad*) want=1;; esac
      run_check "$chk" "$f" "-"; [ "$RC" != "$want" ] && { v=MISMATCH; why+=" $fx rc=$RC: $OUT;"; }
    done
  fi
  printf '%-42s %-5s %-5s %-6s %-8s %s\n' "$t" "$rg" "$rb" "$ru" "$rm_" "$v"
  [ "$v" = MISMATCH ] && { mism=1; mismsg+="MISMATCH $t:$why"$'\n'; }
  [ "$KEEP" = 0 ] && rm -rf "$w"
done
[ -n "$mismsg" ] && printf '\n%s' "$mismsg"
exit $mism
