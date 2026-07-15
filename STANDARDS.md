# Project Standards — os-evals

## Reliability
- **Column-0 guard in meta.yaml parsers**: every `read_task_meta` function must skip lines where `line[:1] in (" ", "\t")` before matching keys, preventing description-block prose from shadowing top-level fields. `run_matrix.py` is the reference; apply to all other parsers in the harness.
- **Sentinel propagation via score records**: sentinel tasks carry `"sentinel": False/True` through the score JSON (set in `score.py`'s `read_task_meta` and included in both `score_run` return paths) so downstream consumers (`stats.py`) filter without re-reading `meta.yaml` — matches the `contaminated` field precedent.

## Exit Code Convention
- `check.sh` uses: `0` = pass, `1` = real task failure, `2` = infra/unscoreable (workspace not retained, auth error, etc.). `score.py` maps `rc==2` to `infra_error: True` and does not count it as a genuine failure.

## Sentinel Tasks
- Sentinel tasks (`sentinel: true` in `meta.yaml`) run at rung 1 only (`run_matrix.py` filters `task_rungs`). They are excluded from pass/fail counts, sign-test, and cost tables in `stats.py`. They appear in a separate `## Difficulty Anchors` section at the bottom of the scorecard.
