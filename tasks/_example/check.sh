#!/bin/bash
set -euo pipefail

# tasks/_example/check.sh
# Evaluates whether the task was completed successfully.
# Reads the full transcript JSON from stdin.
# Exits 0 if pass, non-zero if fail.

# The transcript is a JSON object containing:
#   - messages: array of {role, content} objects
#   - model: model ID used
#   - tokens: {input, output, total}
#   - etc.

# Example checks:
#   - grep transcript for key success indicators (test output, commit message, etc.)
#   - run automated tests if workspace was modified
#   - validate specific assertions in the final state

# TODO: Implement task-specific checks
# For now, always pass (replace with real logic)
exit 0
