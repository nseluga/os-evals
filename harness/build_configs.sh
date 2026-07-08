#!/bin/bash
set -euo pipefail

# harness/build_configs.sh
# Composes configs/rung{1..4} directories from ~/os per a layer manifest.
# Each rung has isolated CLAUDE_CONFIG_DIR with the appropriate layers enabled/disabled.

# Inputs:
#   $1: path to layer manifest file (YAML or JSON describing what to include per rung)
# Outputs:
#   Creates configs/rung{1..4}/ directories with config structure
#   Each has a .env or settings.json controlling CLAUDE_CONFIG_DIR isolation

# TODO: Implementation
echo "build_configs.sh: not implemented" >&2
exit 1
