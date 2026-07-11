#!/bin/bash
set -euo pipefail

# harness/build_configs.sh
# Assembles configs/rung{1..4}/ directories from ~/os.
#
# Isolation mechanism (discovered empirically):
#   CLAUDE_CONFIG_DIR isolates config storage per run, but daemon-based OAuth auth
#   is coupled to ~/.claude/daemon. Changing CLAUDE_CONFIG_DIR breaks auth.
#   SOLUTION: ANTHROPIC_AUTH_TOKEN (OAuth accessToken from keychain) is honored
#   directly and bypasses the daemon, so it works alongside a per-rung
#   CLAUDE_CONFIG_DIR for BOTH bare (rungs 1-3) and non-bare (rung 4) runs.
#
# Why rung 4 is NOT --bare (also discovered empirically):
#   --bare drops the Skill tool entirely in headless `claude -p` (verified: the
#   model reports no Skill tool and cannot invoke any skill). Since rung 4 exists
#   to exercise skills, it must run NON-bare. Non-bare + CLAUDE_CONFIG_DIR +
#   ANTHROPIC_AUTH_TOKEN authenticates fine and stays isolated: personal skills
#   are read from $CLAUDE_CONFIG_DIR/skills, CLAUDE.md from $CLAUDE_CONFIG_DIR/CLAUDE.md,
#   and auto-memory from settings.json's autoMemoryDirectory — none of it touches
#   the real ~/.claude. That lets us curate rung 4's skill set to exactly the
#   skills Nate actually reaches for (see CURATED_SKILLS below) instead of the
#   whole ~38-skill catalog.
#
# Rung layout:
#   rung1: bare claude, empty dir — no context
#   rung2: bare + CLAUDE.md via --add-dir
#   rung3: bare + CLAUDE.md + memory appended inline
#   rung4: non-bare + isolated CLAUDE_CONFIG_DIR — CLAUDE.md + memory (auto-loaded)
#          + ONLY the curated skill set (not the full catalog); token auth
#
# Each rung dir gets:
#   rung.env    — shell env vars (CLAUDE_CONFIG_DIR, ANTHROPIC_AUTH_TOKEN)
#   rung.flags  — extra claude flags (--bare --add-dir ...); empty for rung 4

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

# --- Rung 4: everything (CLAUDE.md + memory + skills), but ONLY the curated skills ---
# Isolated config dir, non-bare (so the Skill tool exists), token auth (so daemon
# OAuth isn't needed). CLAUDE.md + memory are kept exactly as the full setup has
# them; the ONLY narrowing vs. the real ~/.claude is the skill list.
#
# CURATED_SKILLS: rung 4 tests ONLY the dev-team orchestration skills. These are the
# skills whose value is objective (ship hard, complex work quickly and with quality —
# runtime, scalability, security), which is what this eval can actually measure. The
# other curated skills were dropped because their value is subjective/quality-of-judgment
# and pass/fail can't score it. Keep in sync with the task->skill map in SPEC.md.
#
# UNDER TEST (attribution): dev-team, dev-team-auto — the two orchestrators.
# REQUIRED MACHINERY: dt-analyze/dt-engineer/dt-qa/dt-review/dt-fix/dt-ui — the
#   specialists the orchestrators invoke as skills/agents (verified: both SKILL.md
#   files reference them). They MUST be present or the orchestrator can't run and a
#   failure would be wrongly attributed to it. They are not separately attributed.
# DROPPED vs the old catalog: ai-usage-optimizer, baseball-research-advisor — their
#   value is subjective judgment quality, which pass/fail can't score.
CURATED_SKILLS=(
    dev-team
    dev-team-auto
    dt-analyze
    dt-engineer
    dt-qa
    dt-review
    dt-fix
    dt-ui
)

RUNG4="$CONFIGS_DIR/rung4"
rm -rf "$RUNG4"                       # rebuild clean so a shrunk skill set can't leave stragglers
mkdir -p "$RUNG4/memory" "$RUNG4/skills"

# CLAUDE.md — same copy as rung2/rung3 (auto-discovered as $CLAUDE_CONFIG_DIR/CLAUDE.md)
cp "$CLAUDE_DIR/CLAUDE.md" "$RUNG4/CLAUDE.md"

# Memory — snapshot ALL files INCLUDING MEMORY.md (the index), so the real
# auto-memory mechanism loads it (rung 3 inlines instead because --bare skips auto-memory).
if [ -d "$CLAUDE_DIR/memory" ]; then
    for f in "$CLAUDE_DIR/memory/"*.md; do
        [ -f "$f" ] || continue
        cp "$f" "$RUNG4/memory/$(basename "$f")"
    done
fi

# settings.json — enable auto-memory pointed at THIS rung's snapshot (isolated, reproducible)
cat > "$RUNG4/settings.json" << EOF
{
  "autoMemoryEnabled": true,
  "autoMemoryDirectory": "$RUNG4/memory"
}
EOF

# skills/ — symlink ONLY the curated set from $CLAUDE_DIR/skills
missing=()
for s in "${CURATED_SKILLS[@]}"; do
    src="$CLAUDE_DIR/skills/$s"
    if [ -d "$src" ]; then
        ln -s "$src" "$RUNG4/skills/$s"
    else
        missing+=("$s")
    fi
done
if [ "${#missing[@]}" -gt 0 ]; then
    echo "build_configs.sh: ERROR rung4 curated skills not found in $CLAUDE_DIR/skills: ${missing[*]}" >&2
    exit 1
fi

cat > "$RUNG4/rung.env" << EOF
CLAUDE_CONFIG_DIR=$RUNG4
ANTHROPIC_AUTH_TOKEN=$AUTH_TOKEN
EOF
: > "$RUNG4/rung.flags"   # empty: NON-bare (Skill tool must exist), no --add-dir needed

# Verify: rung4/skills exposes EXACTLY the curated set and none of the other ~38.
built_skills="$(cd "$RUNG4/skills" && ls -1 | sort)"
want_skills="$(printf '%s\n' "${CURATED_SKILLS[@]}" | sort)"
if [ "$built_skills" != "$want_skills" ]; then
    echo "build_configs.sh: ERROR rung4 skill set mismatch." >&2
    echo "  built: $(echo "$built_skills" | tr '\n' ' ')" >&2
    echo "  want:  $(echo "$want_skills" | tr '\n' ' ')" >&2
    exit 1
fi
echo "build_configs.sh: rung4 done (isolated, non-bare, token auth; ${#CURATED_SKILLS[@]} curated skills)"

echo "build_configs.sh: all 4 rungs written to $CONFIGS_DIR"
