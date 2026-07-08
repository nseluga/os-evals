#!/usr/bin/env python3
"""
harness/stats.py

Paired sign-test across the 12 tasks per rung-pair.

Inputs:
  Scores JSON from score.py

Outputs:
  Paired sign-test results:
    - Per rung-pair (1 vs 2, 2 vs 3, 3 vs 4, 1 vs 4)
    - "Rung 4 beat rung 1 on 10/12" format
    - Per-task and per-category verdicts (directional, no significance claim)

  Results merged into markdown scorecard template
  Includes pre-committed action thresholds (e.g., layer wins ≤7/12 two runs in a row → prune)
"""

def main():
    raise NotImplementedError("stats.py: not implemented")

if __name__ == "__main__":
    main()
