#!/usr/bin/env python3
"""
harness/score.py

Runs each task's check.sh + parses transcript stats + tokens.

For each run JSON:
  1. Extract task/rung/model metadata
  2. Run check.sh from the task dir, passing transcript as stdin
  3. Record pass/fail (exit code)
  4. Parse transcript for: turn count, retries, reverted edits, tokens, cost
  5. Build per-task and per-category scorecards

Inputs:
  --runs-dir: directory of transcript JSONs (default: runs/)
  --os-sha: git SHA of ~/os repo (for stamp)

Outputs:
  Detailed scores object (JSON) with per-task and per-category verdicts
  Ready for stats.py to compute paired sign-test
"""

def main():
    raise NotImplementedError("score.py: not implemented")

if __name__ == "__main__":
    main()
