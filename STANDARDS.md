# Project Standards — os-evals

## Reliability
- **Column-0 guard in meta.yaml parsers**: every `read_task_meta` function must skip lines where `line[:1] in (" ", "\t")` before matching keys, preventing description-block prose from shadowing top-level fields. `run_matrix.py` is the reference; apply to all other parsers in the harness.
- **Sentinel propagation via score records**: sentinel tasks carry `"sentinel": False/True` through the score JSON (set in `score.py`'s `read_task_meta` and included in both `score_run` return paths) so downstream consumers (`stats.py`) filter without re-reading `meta.yaml` — matches the `contaminated` field precedent.

## Exit Code Convention
- `check.sh` uses: `0` = pass, `1` = real task failure, `2` = infra/unscoreable (workspace not retained, auth error, etc.). `score.py` maps `rc==2` to `infra_error: True` and does not count it as a genuine failure.

## Sentinel Tasks
- Sentinel tasks (`sentinel: true` in `meta.yaml`) run at rung 1 only (`run_matrix.py` filters `task_rungs`). They are excluded from pass/fail counts, sign-test, and cost tables in `stats.py`. They appear in a separate `## Difficulty Anchors` section at the bottom of the scorecard.

## Promotion gate: two-sided check validation
- Before a task is promoted out of `tasks/_draft/`, and before any live `check.sh` is edited, `harness/validate_checks.sh --task <cat>/<name>` must print `OK`. Free: no model calls. `--keep` retains temp workspaces under `$VALIDATE_TMP` (default `$TMPDIR/os-evals-validate`).
- Two sides: a known-good workspace/output must exit 0, a plausible known-bad one must exit 1. Workspace checks (those that read `WORKSPACE_DIR`) must also exit 2 when `WORKSPACE_DIR` is unset and when it points at a nonexistent path. Text-only checks read only the transcript JSON on stdin and have no exit-2 path; their unset/missing columns print N/A.
- Sources, in order: (1) `workspace.ref` with `solution_sha:` -> good = `git archive <solution_sha>`, bad = base `sha:` (`X^` resolved via rev-parse), `setup.sh` run in each; (2) `tests/good/` and `tests/bad/` fixture dirs inside the task dir. For workspace checks they are the workspace contents; for text checks each holds a `transcript.json` (`{"result": "..."}`) fed on stdin exactly as `score.py run_check` does; (3) otherwise UNVALIDATED.
- A check that cannot be faked cheaply gets `anchor_only: true` at column 0 in `meta.yaml` with a `# validate_checks: <reason>` comment; the script reports it UNVALIDATED.
- If a fixture fails, fix the fixture only when the fixture was wrong. If the check passes a bad answer or fails a good one, report MISMATCH and fix the check deliberately, never to make the gate green.
