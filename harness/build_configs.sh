#!/bin/bash
set -euo pipefail

# harness/build_configs.sh [--os-sha <sha>]
# Builds configs/<sha>/{bare,claude-md,memory,skills,full}/ from a git snapshot of ~/os
# (default: ~/os HEAD), so the ~/os SHA under test is the code actually run, not a label.
#
# Snapshot: `git -C ~/os archive <sha>` -> configs/<sha>/src/. Each non-bare layer is a
# CLAUDE_CONFIG_DIR that symlinks/copies pieces of src/:
#   bare       --bare, empty config dir, no context
#   claude-md  CLAUDE.md + settings {autoMemoryEnabled:false}, no hooks
#   memory     + autoMemoryDirectory -> src/knowledge/memory, UserPromptSubmit hook running
#              src/scripts/memory-relevance-hook.py (resolves memory relative to its own file)
#   skills     + skills/ and agents/
#   full       + output-styles/ and the live-shaped settings (model, env, outputStyle...) with
#              every hook except the memory hook stripped, ~/os paths rewritten to src/
# Non-bare layers run with `--setting-sources user` so only the layer's own config loads.
# HOME isolation (default on; --no-home-isolation to drop): the claude subprocess gets
# HOME=configs/<sha>/home, where ~/os -> src/, so CLAUDE.md's `~/os/...` pointers read the
# snapshot instead of live disk (bare gets an empty home-bare/). GIT_CONFIG_GLOBAL points at
# the real ~/.gitconfig so git identity survives. Limit: an absolute /Users/<me>/os path
# still reads live files. python3/node/npm/git/pnpm here are absolute-path binaries and need
# no extra root vars (checked); PNPM_HOME is already absolute in the inherited env.
#
# settings.json is NOT tracked in ~/os (it lives only at ~/.claude/settings.json), so the
# `full` settings come from live $CLAUDE_DIR/settings.json and are constant across SHAs.
# Personal overlay (gitignored files symlinked from ~/personal-os) is copied from live state
# into src/ when present, also constant across SHAs. Plugins are stripped (known gap).
#
# Auth: NO token is written to disk. rung.env holds only CLAUDE_CONFIG_DIR/HOME/GIT_CONFIG_GLOBAL.
# The token lives in keychain item `os-evals-claude-token`; harness/run_matrix.py reads it once per
# process and injects it into the claude subprocess env, and the memory hook wrapper (see
# snapshot_settings._ENV_WRAP) re-reads it. To mint and store it (Nate runs these; this script never does):
#   claude setup-token
#   security add-generic-password -a os-evals -s os-evals-claude-token -w '<token>'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIGS_DIR="${CONFIGS_DIR:-$REPO_ROOT/configs}"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
OS_DIR="${OS_DIR:-$HOME/os}"
PERSONAL_DIR="${PERSONAL_DIR:-$HOME/personal-os}"
REQ_SHA=""
HOME_ISOLATION=1
REAL_HOME="$HOME"

while [ $# -gt 0 ]; do
    case "$1" in
        --os-sha) REQ_SHA="$2"; shift 2;;
        --no-home-isolation) HOME_ISOLATION=0; shift;;
        *) echo "build_configs.sh: unknown arg: $1" >&2; exit 1;;
    esac
done

SHA="$(git -C "$OS_DIR" rev-parse --short "${REQ_SHA:-HEAD}^{commit}" 2>/dev/null)" || {
    echo "build_configs.sh: ERROR sha '${REQ_SHA:-HEAD}' is not in $OS_DIR history" >&2
    exit 2
}
BASE="$CONFIGS_DIR/$SHA"
SRC="$BASE/src"
echo "build_configs.sh: os sha=$SHA -> $BASE"
if [ "$SHA" = "$(git -C "$OS_DIR" rev-parse --short HEAD)" ]; then
    n_dirty="$(git -C "$OS_DIR" status --porcelain | wc -l | tr -d ' ')"
    [ "$n_dirty" -gt 0 ] && echo "build_configs.sh: WARNING snapshot is the committed state of HEAD; $n_dirty uncommitted files in $OS_DIR are not included"
fi

# --- snapshot ---
# A previous build's src/ is read-only (chmod a-w below); restore write so rm can delete it.
[ -e "$BASE" ] && chmod -R u+w "$BASE"
rm -rf "$BASE"
mkdir -p "$SRC"
git -C "$OS_DIR" archive "$SHA" | tar -x -C "$SRC"
[ -f "$SRC/CLAUDE.md" ] || { echo "build_configs.sh: ERROR no CLAUDE.md in snapshot $SHA" >&2; exit 2; }
[ -f "$SRC/scripts/memory-relevance-hook.py" ] || echo "build_configs.sh: WARNING no memory hook at $SHA; memory/skills/full layers get no hook" >&2

# --- personal overlay: gitignored symlinks into ~/personal-os, copied from live state ---
n_personal=0
for sub in skills agents knowledge/memory; do
    [ -d "$OS_DIR/$sub" ] || continue
    for p in "$OS_DIR/$sub"/*; do
        [ -L "$p" ] || continue
        case "$(readlink "$p")" in "$PERSONAL_DIR"/*) ;; *) continue;; esac
        [ -e "$p" ] || continue
        [ -e "$SRC/$sub/$(basename "$p")" ] && continue
        mkdir -p "$SRC/$sub"
        cp -RL "$p" "$SRC/$sub/"
        n_personal=$((n_personal + 1))
    done
done
echo "build_configs.sh: personal overlay: $n_personal live ~/personal-os entries (memory/skills/agents) copied into src/, held constant across SHAs"
echo "build_configs.sh: known gap: enabledPlugins stripped (ponytail, impeccable, ui-ux-pro-max, claude-code-setup not loaded)"

printf '%s\n' "$SHA" > "$SRC/.evals-snapshot-id"
if [ "$HOME_ISOLATION" -eq 1 ]; then
    mkdir -p "$BASE/home" "$BASE/home-bare"
    ln -s "$SRC" "$BASE/home/os"
fi

write_env() (  # $1 = layer dir, $2 = HOME dir for this layer; subshell so umask stays local
    umask 077  # rung.env holds no token (keychain only), but keep it private anyway
    printf 'CLAUDE_CONFIG_DIR=%s\n' "$1" > "$1/rung.env"
    if [ "$HOME_ISOLATION" -eq 1 ]; then
        printf 'HOME=%s\n' "$2" >> "$1/rung.env"
        [ -f "$REAL_HOME/.gitconfig" ] && printf 'GIT_CONFIG_GLOBAL=%s\n' "$REAL_HOME/.gitconfig" >> "$1/rung.env"
    fi
    chmod 600 "$1/rung.env"
)

# --- bare ---
mkdir -p "$BASE/bare"
write_env "$BASE/bare" "$BASE/home-bare"
printf '%s\n' '--bare' > "$BASE/bare/rung.flags"
chmod 600 "$BASE/bare/rung.env"

# --- non-bare layers ---
for layer in claude-md memory skills full; do
    d="$BASE/$layer"
    mkdir -p "$d"
    cp "$SRC/CLAUDE.md" "$d/CLAUDE.md"
    case "$layer" in skills|full)
        ln -s "$SRC/skills" "$d/skills"
        [ -d "$SRC/agents" ] && ln -s "$SRC/agents" "$d/agents";;
    esac
    if [ "$layer" = full ] && [ -d "$SRC/output-styles" ]; then ln -s "$SRC/output-styles" "$d/output-styles"; fi
    LAYER="$layer" SNAP="$SRC" LIVE="$CLAUDE_DIR/settings.json" OUT="$d/settings.json" \
        PYTHONPATH="$SCRIPT_DIR" python3 -c "
import json, os
from snapshot_settings import layer_settings
live = json.load(open(os.environ['LIVE']))
json.dump(layer_settings(os.environ['LAYER'], live, os.environ['SNAP']), open(os.environ['OUT'], 'w'), indent=2)
"
    write_env "$d" "$BASE/home"
    printf '%s\n' '--setting-sources user' > "$d/rung.flags"
done

# Freeze the snapshot so one run cannot change what a later run sees. Layer dirs and home/
# stay writable (Claude Code keeps session state there). memory-relevance-hook.py appends to
# src/outputs/memory-hook-errors.log, so that one directory stays writable.
mkdir -p "$SRC/outputs"
chmod -R a-w "$SRC"
chmod -R u+w "$SRC/outputs"

echo "build_configs.sh: done -> $BASE/{bare,claude-md,memory,skills,full}"
