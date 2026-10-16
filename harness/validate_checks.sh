#!/bin/bash
# harness/validate_checks.sh — free (no model calls) two-sided validation of every live task's check.sh.
#   good workspace/transcript -> exit 0; bad -> exit 1;
#   workspace checks only: WORKSPACE_DIR unset -> 2, WORKSPACE_DIR nonexistent -> 2.
#   Text-only checks (never mention WORKSPACE_DIR) have no exit-2 path: unset/missing print N/A.
#   Checks that mention TRACE_FILE get TRACE_FILE=<fixture>/trace.jsonl when the fixture holds one, and a
#   `trace` column <unset rc>/<missing rc>: good workspace with TRACE_FILE unset -> 0 (skipped), set to a
#   nonexistent path -> 2. With any tests/*/trace.jsonl, every tests/good*|bad* dir also runs as a
#   workspace fixture (good* -> 0, bad* -> 1), including on the solution_sha path.
#   Every check runs with OS_EVALS_VALIDATE=1 (score.py never sets it): lets a check rebuild a fixture-only workspace.
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
run_check() { # $1=check.sh $2=stdin file $3=WORKSPACE_DIR value or "-" for unset $4=TRACE_FILE value or "-"/absent for unset
  local c="$1" in="$2" ws="$3" tr="${4:--}" a=(env -u WORKSPACE_DIR -u TRACE_FILE OS_EVALS_VALIDATE=1)
  [ "$ws" != "-" ] && a+=("WORKSPACE_DIR=$ws")
  [ "$tr" != "-" ] && a+=("TRACE_FILE=$tr")
  OUT="$("${a[@]}" "$c" <"$in" 2>&1)"; RC=$?
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

printf '%-42s %-5s %-5s %-6s %-8s %-6s %s\n' task good bad unset missing trace verdict
mism=0; mismsg=""
for t in "${tasks[@]}"; do
  td="$TASKS/$t"; chk="$td/check.sh"; w="$TMP/${t//\//__}"; rm -rf "$w"; mkdir -p "$w"
  textonly=0; grep -q WORKSPACE_DIR "$chk" || textonly=1
  tmention=0; grep -q TRACE_FILE "$chk" && tmention=1
  # meta.yaml anchor_only at column 0 => UNVALIDATED by design
  if grep -q '^anchor_only:[[:space:]]*true' "$td/meta.yaml"; then
    printf '%-42s %-5s %-5s %-6s %-8s %-6s %s\n' "$t" - - - - - UNVALIDATED; continue; fi
  ref="$td/workspace.ref"; sol=""; origin=""
  [ -f "$ref" ] && { sol="$(ref_field "$ref" solution_sha)"; origin="$(ref_field "$ref" origin)"; base="$(ref_field "$ref" sha)"; }
  g=""; b=""; gin=/dev/null; bin=/dev/null; err=""; shapath=0
  if [ -n "$sol" ] && [ -n "$origin" ]; then
    restore "$origin" "$sol" "$w/good" && restore "$origin" "$base" "$w/bad" || err="restore failed"
    [ -z "$err" ] && { provision "$td" "$w/good" "$t" && provision "$td" "$w/bad" "$t" || err="setup failed"; }
    g="$w/good"; b="$w/bad"; shapath=1
  elif [ -d "$td/tests/good" ] && [ -d "$td/tests/bad" ]; then
    if [ "$textonly" = 1 ]; then
      gin="$td/tests/good/transcript.json"; bin="$td/tests/bad/transcript.json"; g="$w/good"; b="$w/bad"; mkdir -p "$g" "$b"
    else
      cp -R "$td/tests/good" "$w/good"; cp -R "$td/tests/bad" "$w/bad"; g="$w/good"; b="$w/bad"
      echo '{"result":""}' >"$w/empty.json"; gin="$w/empty.json"; bin="$gin"
      [ -f "$g/transcript.json" ] && gin="$g/transcript.json"; [ -f "$b/transcript.json" ] && bin="$b/transcript.json"
    fi
  else
    printf '%-42s %-5s %-5s %-6s %-8s %-6s %s\n' "$t" - - - - - UNVALIDATED; continue
  fi
  [ -n "$err" ] && { printf '%-42s %s\n' "$t" "MISMATCH ($err)"; mism=1; continue; }
  # workspace checks with solution_sha get empty stdin JSON too
  [ "$gin" = /dev/null ] && { echo '{"result":""}' >"$w/empty.json"; gin="$w/empty.json"; bin="$gin"; }
  if [ "$textonly" = 1 ]; then ws_g="-"; ws_b="-"; else ws_g="$g"; ws_b="$b"; fi
  # TRACE_FILE only where the fixture ships a trace.jsonl (the solution_sha archives never do -> unset)
  trg=-; trb=-
  if [ "$textonly" = 1 ]; then [ -f "$td/tests/good/trace.jsonl" ] && trg="$td/tests/good/trace.jsonl"; [ -f "$td/tests/bad/trace.jsonl" ] && trb="$td/tests/bad/trace.jsonl"
  else [ -f "$g/trace.jsonl" ] && trg="$g/trace.jsonl"; [ -f "$b/trace.jsonl" ] && trb="$b/trace.jsonl"; fi
  run_check "$chk" "$gin" "$ws_g" "$trg"; rg=$RC; og="$OUT"
  run_check "$chk" "$bin" "$ws_b" "$trb"; rb=$RC; ob="$OUT"
  if [ "$textonly" = 1 ]; then ru="N/A"; rm_="N/A"; else
    run_check "$chk" "$gin" "-"; ru=$RC; ou="$OUT"
    run_check "$chk" "$gin" "$w/does-not-exist"; rm_=$RC; om="$OUT"; fi
  # trace column: only for checks that read TRACE_FILE. Unset -> trace checks skipped (good still 0);
  # set but missing -> infra exit 2.
  rtu="N/A"; rtm="N/A"
  if [ "$tmention" = 1 ]; then
    run_check "$chk" "$gin" "$ws_g" "-"; rtu=$RC; otu="$OUT"
    run_check "$chk" "$gin" "$ws_g" "$w/no-such-trace.jsonl"; rtm=$RC; otm="$OUT"; fi
  v=OK; why=""
  [ "$tmention" = 1 ] && [ "$rtu" != 0 ] && { v=MISMATCH; why+=" trace-unset rc=$rtu: ${otu:-};"; }
  [ "$tmention" = 1 ] && [ "$rtm" != 2 ] && { v=MISMATCH; why+=" trace-missing rc=$rtm: ${otm:-};"; }
  [ "$rg" != 0 ] && { v=MISMATCH; why+=" good rc=$rg: $og;"; }
  [ "$rb" != 1 ] && { v=MISMATCH; why+=" bad rc=$rb: $ob;"; }
  [ "$textonly" = 0 ] && [ "$ru" != 2 ] && { v=MISMATCH; why+=" unset rc=$ru: ${ou:-};"; }
  [ "$textonly" = 0 ] && [ "$rm_" != 2 ] && { v=MISMATCH; why+=" missing rc=$rm_: ${om:-};"; }
  # extra text-only fixtures (good2.., bad2..: usually real stored answers) must agree too
  if [ "$textonly" = 1 ]; then
    for f in "$td"/tests/good?*/transcript.json "$td"/tests/bad?*/transcript.json; do
      [ -f "$f" ] || continue
      fx="$(basename "$(dirname "$f")")"; want=0; case "$fx" in bad*) want=1;; esac
      trf=-; [ -f "$(dirname "$f")/trace.jsonl" ] && trf="$(dirname "$f")/trace.jsonl"
      run_check "$chk" "$f" "-" "$trf"; [ "$RC" != "$want" ] && { v=MISMATCH; why+=" $fx rc=$RC: $OUT;"; }
    done
  fi
  # workspace fixtures with traces: every tests/good*|bad* dir as a workspace with TRACE_FILE set. The
  # solution_sha path runs all of them (it never read tests/ before); the tests/ path already ran good+bad.
  frows=
  if [ "$textonly" = 0 ] && compgen -G "$td/tests/*/trace.jsonl" >/dev/null; then
    for d in "$td"/tests/good* "$td"/tests/bad*; do
      [ -d "$d" ] || continue; fx="$(basename "$d")"
      [ "$shapath" = 0 ] && case "$fx" in good|bad) continue;; esac
      want=0; case "$fx" in bad*) want=1;; esac
      cp -R "$d" "$w/fx-$fx"; fin="$w/empty.json"; [ -f "$d/transcript.json" ] && fin="$d/transcript.json"
      [ -f "$w/empty.json" ] || echo '{"result":""}' >"$w/empty.json"
      trf=-; [ -f "$w/fx-$fx/trace.jsonl" ] && trf="$w/fx-$fx/trace.jsonl"
      run_check "$chk" "$fin" "$w/fx-$fx" "$trf"; fv=OK
      [ "$RC" != "$want" ] && { fv=MISMATCH; v=MISMATCH; why+=" $fx rc=$RC: $OUT;"; }
      frows+="$(printf '  %-40s rc=%-3s want=%s TRACE_FILE=%s %s' "[$fx]" "$RC" "$want" "$([ "$trf" = - ] && echo unset || echo fixture)" "$fv")"$'\n'
    done
  fi
  printf '%-42s %-5s %-5s %-6s %-8s %-6s %s\n' "$t" "$rg" "$rb" "$ru" "$rm_" "$rtu/$rtm" "$v"
  [ -n "$frows" ] && printf '%s' "$frows"
  [ "$v" = MISMATCH ] && { mism=1; mismsg+="MISMATCH $t:$why"$'\n'; }
  [ "$KEEP" = 0 ] && rm -rf "$w"
done
[ -n "$mismsg" ] && printf '\n%s' "$mismsg"
exit $mism
