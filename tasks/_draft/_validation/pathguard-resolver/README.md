# pathguard-resolver — retained reference solutions (NOT part of the live task)

These reconstruct the two-sided validation references described in
`tasks/_draft/REVIEW.md` (the originals lived only in the authoring job's tmp dir).
They live under `tasks/_draft/_validation/` so `find_tasks()` auto-excludes them
(any path segment starting with `_` is skipped) — they must never sit inside the
live task dir, or `seed/` would copy a solution into the run workspace.

- `good/` — realpath + commonpath containment → `check.sh` exits **0**.
- `bad/`  — join + normpath + `startswith` → `check.sh` exits **1** (fails the
  symlink-escape and sibling-prefix-bypass security checks only).

To re-validate a promoted task, build a workspace = `seed/` + one of these
solution trees, then run the task's `check.sh` with `WORKSPACE_DIR` pointed at it.
