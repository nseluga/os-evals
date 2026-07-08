#!/bin/bash
set -euo pipefail

# tasks/_example/check.sh
# Evaluates whether the task was completed successfully.
# Reads the full transcript JSON from stdin.
# Exits 0 if pass, non-zero if fail.

# The transcript is a JSON object (from claude -p --output-format json) containing:
#   - result           : string — the final text output from the model
#   - is_error         : bool
#   - num_turns        : int
#   - total_cost_usd   : float
#   - usage            : object with input_tokens, cache_read_input_tokens,
#                        cache_creation_input_tokens, output_tokens
#   - stop_reason      : string
#   - _meta            : object — task/rung/model metadata added by run_matrix.py
#
# NOTE: There is NO messages array. Checks can only evaluate the final `result` text.
# For code tasks, the workspace state (files written) must be checked via filesystem.

# Example checks:
#   - grep transcript for key success indicators (test output, commit message, etc.)
#   - run automated tests if workspace was modified
#   - validate specific assertions in the final state

# TODO: Implement task-specific checks
# For now, always pass (replace with real logic)
exit 0
