#!/bin/bash
set -euo pipefail

# harness/build_configs.sh
# Assembles configs/rung{1..4}/ directories from ~/os.
#
# Isolation mechanism (discovered empirically):
#   CLAUDE_CONFIG_DIR isolates config storage per run, but daemon-based OAuth auth
#   is coupled to ~/.claude/daemon. Changing CLAUDE_CONFIG_DIR breaks auth.
#   SOLUTION: --bare mode + ANTHROPIC_AUTH_TOKEN (OAuth accessToken from keychain)
#   bypasses the daemon entirely. --add-dir injects per-rung CLAUDE.md content.
#
# Rung layout:
#   rung1: bare claude, empty dir — no context
#   rung2: bare + CLAUDE.md via --add-dir
#   rung3: bare + CLAUDE.md + memory appended inline
#   rung4: normal claude (no --bare), default ~/.claude — full setup with skills
#
# Each rung dir gets:
#   rung.env    — shell env vars (CLAUDE_CONFIG_DIR, ANTHROPIC_AUTH_TOKEN)
#   rung.flags  — extra claude flags (--bare --add-dir ...)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIGS_DIR="$REPO_ROOT/configs"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

echo "build_configs.sh: CLAUDE_DIR=$CLAUDE_DIR"

# Extract OAuth access token from macOS keychain
get_auth_token() {
    python3 -c "
import subprocess, json, sys
result = subprocess.run(
    ['security', 'find-generic-password', '-s', 'Claude Code-credentials', '-w'],
    capture_output=True, text=True
)
if result.returncode != 0:
    print('ERROR: could not read keychain', file=sys.stderr)
    sys.exit(1)
blob = json.loads(result.stdout.strip())
token = blob['claudeAiOauth']['accessToken']
print(token, end='')
"
}

AUTH_TOKEN=$(get_auth_token)
if [ -z "$AUTH_TOKEN" ]; then
    echo "ERROR: could not extract auth token from keychain" >&2
    exit 1
fi
echo "build_configs.sh: auth token extracted (length=${#AUTH_TOKEN})"

# --- Rung 1: bare claude, no context ---
RUNG1="$CONFIGS_DIR/rung1"
mkdir -p "$RUNG1"
cat > "$RUNG1/rung.env" << EOF
CLAUDE_CONFIG_DIR=$RUNG1
ANTHROPIC_AUTH_TOKEN=$AUTH_TOKEN
EOF
printf '%s\n' '--bare' > "$RUNG1/rung.flags"
echo "build_configs.sh: rung1 done (bare, no context)"

# --- Rung 2: CLAUDE.md + knowledge routing ---
RUNG2="$CONFIGS_DIR/rung2"
mkdir -p "$RUNG2"
cp "$CLAUDE_DIR/CLAUDE.md" "$RUNG2/CLAUDE.md"
cat > "$RUNG2/rung.env" << EOF
CLAUDE_CONFIG_DIR=$RUNG2
ANTHROPIC_AUTH_TOKEN=$AUTH_TOKEN
EOF
printf '%s\n' "--bare" "--add-dir $RUNG2" > "$RUNG2/rung.flags"
echo "build_configs.sh: rung2 done (CLAUDE.md only)"

# --- Rung 3: rung2 + memory (behavior instructions) ---
RUNG3="$CONFIGS_DIR/rung3"
mkdir -p "$RUNG3/memory"
cp "$CLAUDE_DIR/CLAUDE.md" "$RUNG3/CLAUDE.md"

# Copy individual memory files (not MEMORY.md index)
if [ -d "$CLAUDE_DIR/memory" ]; then
    for f in "$CLAUDE_DIR/memory/"*.md; do
        [ -f "$f" ] || continue
        fname="$(basename "$f")"
        [ "$fname" = "MEMORY.md" ] && continue
        cp "$f" "$RUNG3/memory/$fname"
    done
fi

# Append memory content inline to CLAUDE.md (--bare skips auto-memory)
if ls "$RUNG3/memory/"*.md 2>/dev/null | grep -q .; then
    {
        printf '\n\n---\n# Injected Memory (behavior instructions)\n\n'
        for f in "$RUNG3/memory/"*.md; do
            [ -f "$f" ] || continue
            printf '## %s\n\n' "$(basename "$f")"
            cat "$f"
            printf '\n\n'
        done
    } >> "$RUNG3/CLAUDE.md"
fi

cat > "$RUNG3/rung.env" << EOF
CLAUDE_CONFIG_DIR=$RUNG3
ANTHROPIC_AUTH_TOKEN=$AUTH_TOKEN
EOF
printf '%s\n' "--bare" "--add-dir $RUNG3" > "$RUNG3/rung.flags"
echo "build_configs.sh: rung3 done (CLAUDE.md + memory)"

# --- Rung 4: full ~/.claude, normal auth, skills auto-loaded ---
# No CLAUDE_CONFIG_DIR override, no --bare. Daemon auth, full setup.
RUNG4="$CONFIGS_DIR/rung4"
mkdir -p "$RUNG4"
: > "$RUNG4/rung.env"    # empty: no overrides
: > "$RUNG4/rung.flags"  # empty: no extra flags
echo "build_configs.sh: rung4 done (full ~/.claude, normal auth)"

echo "build_configs.sh: all 4 rungs written to $CONFIGS_DIR"
