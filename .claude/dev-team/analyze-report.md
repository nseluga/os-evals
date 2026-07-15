# Analysis Report
**Task:** Item 4: Add `repeat` support for noisy tasks
**Date:** 2026-07-13

## Relevant Files

`/Users/nateseluga/os-evals/harness/run_matrix.py` — orchestrates task×rung×model loop (line 458-465); `run_one()` (line 300-432) executes single run and names output; `read_task_meta()` (line 103-137) parses meta.yaml; `_slug()` (line 48-50) converts task path to filename token

`/Users/nateseluga/os-evals/harness/score.py` — scores one transcript (line 103-173); `score_run()` reads filename stem to extract task/rung/model (line 109); `run_check()` (line 54-82) runs check.sh; main loop (line 192-203) reads `*.json` from runs_dir glob

`/Users/nateseluga/os-evals/harness/stats.py` — groups scores by (task, rung, model) into `by_task_rung` dict (line 36-39); `_pass_map()` (line 108-114) builds (task, rung) → passed lookup; verdict section uses `pm.get((t, r))` for pass/fail (line 130-207); cost aggregation sums per-rung (line 82-97)

`/Users/nateseluga/os-evals/tasks/writing/portfolio-writeup/meta.yaml` — currently has: category, contaminated, group, curated_skill, description; NO repeat key

`/Users/nateseluga/os-evals/tasks/coding/pir-workload-feature/meta.yaml` — same structure; NO repeat key

## Data Flow

1. **run_matrix**: main loop iterates task → rung → model (line 458-460); calls `read_task_meta()` (line 315) to get timeout_sec/multi_turn/curated_skill
2. **run_one**: generates run_id as `{ts}_{_slug(task)}_rung{rung}_{model}` (line 336); saves to `{run_id}.json` (line 420)
3. **score.py**: globs `*.json` (line 186); score_run() extracts task from `_meta.task` or filename stem split `[1]` (line 109); adds all fields to score record (line 132-173)
4. **stats.py**: groups scores by (task, rung, model) tuple as dict key (line 38-39); builds pass matrix (task, rung) → bool (line 108-114); emits verdicts using pass matrix lookups

## Patterns to Follow

- `read_task_meta()` uses regex-like key parsing: column-0 check (line 124), key split on first `:`, value extract strips `#` comments (line 128-136)
- Filename format is `{timestamp}_{task_slug}_rung{N}_{model}.json`; task_slug = task with `/` → `-` (line 48-50)
- `_meta` dict injected into transcript JSON at run end (line 402-418); contains task/rung/model/timestamp/multi_turn/skill_fired/etc.
- Score record schema: file, task, rung, model, passed, check_rc, infra_error, check_output, plus stats (turns/tokens/cost) — one record per run file
- Stats.py groups by (task, rung, model) tuple; when repeat>1 must emit both individual records AND one synthetic majority-vote record

## Likely Changes

`tasks/writing/portfolio-writeup/meta.yaml` (line 1-31) — add `repeat: 3` at top level

`tasks/coding/pir-workload-feature/meta.yaml` (line 1-36) — add `repeat: 3` at top level

`harness/run_matrix.py`: line 103-137 `read_task_meta()` — parse `repeat:` key (default 1); line 300-307 `run_one()` signature unchanged; line 435-468 main() — wrap run_one call in repeat loop (for i in range(repeat)); line 336 run_id generation — append `_r{i}` suffix when i > 0; line 402-418 `_meta` dict — add `repeat_index: i` and `repeat_total: repeat` fields

`harness/score.py`: line 103-173 `score_run()` — detect `_r{N}` suffix in filename (extract via regex); emit `is_repeat_individual: true` for repeat runs; logic unchanged for individual scoring

`harness/score.py`: after line 204 in main() — NEW post-processing pass: group scores by (task, rung, model); for each group, find `_r{i}` individuals; if individuals exist (len >= 2), compute majority-vote passed bool; emit synthetic record with `repeat_majority: true`, all individual repeat indices in filename, cost = sum of individuals

`harness/stats.py`: line 36-39 compute_stats() — filter out individual repeats (`is_repeat_individual == true`) from by_task_rung dict; use only majority-vote records (`repeat_majority == true`) when available; line 82-97 token_summary() — skip individual repeats, use majority record cost (sum of components)

`harness/stats.py`: line 130-207 verdict_section() — when rendering pass matrix, check for repeat annotation; if score has repeat_majority + individual count, show `✓(K/N)` or `✗(K/N)` format; line 137-139 rung pass rate — exclude individual repeats from denominator (use only one record per logical task/rung cell)

## Risks

- Filename parsing in score.py (line 109) relies on `_meta.task` fallback; must ensure repeat suffix `_r{i}` doesn't break stem split — test edge case of task names containing numbers or hyphens
- By_task_rung dict (stats.py line 36-39) uses (task, rung, model) tuple as key; majority record must use same key as individuals for dedup to work
- Cost aggregation (stats.py line 92-93) currently sums by rung; majority record cost = sum(individual costs) risks double-counting if not filtered correctly
- Individual repeat records must be marked with `is_repeat_individual: true` flag in score record so stats.py can identify and exclude them from pass counts
- Multi-turn tasks with repeat may hit orchestrator state issues (git worktree branches reused across runs) — ensure cleanup between repeats or isolate per repeat index

