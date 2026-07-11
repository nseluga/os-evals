# rangestats-engine — retained reference solutions (NOT part of the live task)

Reconstructs the two-sided validation references from `tasks/_draft/REVIEW.md`
(originals lived only in the authoring job's tmp dir). Kept under
`tasks/_draft/_validation/` so `find_tasks()` auto-excludes them.

- `good/` — dual Fenwick / BIT keyed on the value domain, O(log domain) per op →
  `check.sh` exits **0** (perf + scalability pass with wide margin).
- `bad/`  — list + per-query linear scan, O(N) per query → `check.sh` exits **1**
  (correctness passes, then the SIGALRM-guarded performance and scalability gates
  fail). NOTE: the bad run takes ~45s wall (two alarms fire).

Re-validate a promoted task by building a workspace = `seed/` + one solution tree,
then running the task's `check.sh` with `WORKSPACE_DIR` at it.
