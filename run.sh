#!/bin/bash
set -euo pipefail

# run.sh
# Top-level orchestrator: runs one full iteration of the eval matrix.
# Stamps the ~/os git SHA, calls harness scripts in order, and outputs a scorecard.

# Inputs: (none — reads from frozen ~/os state, task configs)
# Outputs: scorecard markdown to scorecards/{timestamp}-{os-sha}.md
#          run transcript JSONs to runs/

# TODO: Implementation
echo "run.sh: not implemented" >&2
exit 1
