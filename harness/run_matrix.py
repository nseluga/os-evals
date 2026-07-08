#!/usr/bin/env python3
"""
harness/run_matrix.py

Loops task × rung × model → claude -p → saves transcript JSON.

For each combination:
  1. Load task prompt from tasks/{category}/{task}/prompt.md
  2. Load workspace ref (git SHA + tarball fallback)
  3. Invoke: claude -p --config configs/rung{N} < prompt.md
  4. Capture full transcript JSON
  5. Save to runs/{timestamp}_{task}_{rung}_{model}.json

Inputs:
  --tasks TASK_LIST: comma-separated task names (default: all in tasks/)
  --rungs RUNG_LIST: comma-separated rung numbers (default: 1,2,3,4)
  --models MODEL_LIST: comma-separated model IDs (default: sonnet-4.6,opus-4.8)

Outputs:
  JSON transcripts to runs/ directory
  Exit 0 if all runs succeed, non-zero otherwise
"""

def main():
    raise NotImplementedError("run_matrix.py: not implemented")

if __name__ == "__main__":
    main()
