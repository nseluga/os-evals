# Dev-team memory log

## 2026-07-13 — dev-team-auto — Item 1: Fix duplicate-run accumulation in runs/
- **Outcome:** DONE — 1 attempt, light track, branch fix/harness-suite-defects, commit 78b0f83
- **What happened:** Added 4-line rm -f cleanup block in run.sh after mkdir -p and before matrix run; QA verified cleanup fires before run_matrix.py call (line 53 vs 97)
- **What worked:** Direct single-file edit; behavioral simulation of stale file removal confirmed correct
- **What failed:** none
- **Remember next run:** run.sh uses $RUNS_DIR variable consistently — any future cleanup additions should use that variable, not hardcoded "runs/" path

## 2026-07-13 — dev-team-auto — Item 2: Mark dashboard-digest as difficulty sentinel
- **Outcome:** DONE — 2 attempts (1 engineer + 1 fix pass), full track, branch fix/harness-suite-defects, commit ea05b36
- **What happened:** 3-part change: meta.yaml sentinel flag, run_matrix.py rung-filter, stats.py Difficulty Anchors section. Engineer also modified score.py to propagate sentinel through score records so stats.py doesn't re-read meta
- **What worked:** Propagating sentinel via score records (not re-reading meta.yaml in stats.py) was the right call; review caught the missing indentation guard in score.py's read_task_meta vs the one already in run_matrix.py
- **What failed:** score.py's read_task_meta lacked the column-0 indentation guard present in run_matrix.py — description text containing "sentinel: true" would silently misclassify tasks
- **Remember next run:** Both run_matrix.py and score.py have independent read_task_meta implementations — any parsing change must be applied to both. The column-0 guard (`if line[:1] in (" ", "\t"): continue`) is the critical safety check

## 2026-07-13 — dev-team-auto — Item 3: Remove "elevate" from portfolio-writeup blacklist
- **Outcome:** DONE — 1 attempt, trivial track, branch fix/harness-suite-defects, commit 047f4f8
- **What happened:** Removed "elevate" from check.sh blacklist; verified buzz_hits=[] for technical context; cutting-edge still triggers exit 1
- **What worked:** Direct single-file edit; behavioral spot-check confirmed both sides in one python3 call
- **What failed:** Initially edited main checkout instead of worktree — edits for items on a worktree branch must be made in the worktree path
- **Remember next run:** Changes always belong on the worktree branch path (`.claude/worktrees/fix-harness-suite-defects/`), not the main checkout. Main checkout tracks a different branch and won't be merged

## 2026-07-13 — dev-team-auto — Item 4: Add repeat support for noisy tasks
- **Outcome:** DONE — 2 attempts (1 engineer + 1 fix), full track, branch fix/harness-suite-defects, commit 3c3de4f
- **What happened:** 5-file change adding repeat loop in run_matrix, majority-vote in score.py, (K/N) annotation in stats.py. Review caught premature majority on partial groups and missing _effective_scores call in cross_model_section
- **What worked:** Grouping by (task, rung, model) tuple correct; workspace isolation per repeat run (separate .ws dirs) was already correct; cost aggregation with `or 0` handled None correctly
- **What failed:** score.py emitted majority record even when n < repeat_total (partial transcript set); cross_model_section in stats.py skipped the _effective_scores filter unlike the other 4 call sites
- **Remember next run:** When adding a new filter helper (_effective_scores, _is_sentinel), search for ALL sites that build score tables — cross_model_section is a separate code path from render_markdown's main pipeline and is easy to miss. grep for the unfiltered `scores` or `all_scores` variable before declaring a filtering change complete

## 2026-07-13 — dev-team-auto — Item 5: Add harness unit tests for pure functions
- **Outcome:** DONE — 1 attempt, light track, branch fix/harness-suite-defects, commit 91ed75f
- **What happened:** Created test_harness_pure_fns.py covering detect_skill_fired, _parse_stream, looks_like_auth_error; 17 checks, all pass
- **What worked:** Reading the actual function implementations before writing tests — the PLAN.md spec described expected behavior ("Authentication" → True, "403" → True) that didn't match actual patterns (authentication_error, unauthorized)
- **What failed:** none
- **Remember next run:** PLAN.md test specs for function behavior can be illustrative rather than literal — always read the actual implementation before writing tests, not just the spec
