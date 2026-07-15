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

## 2026-07-15 — dev-team-auto — Item 1: Fix pir-workload-feature timeout + two-sided validation
- **Outcome:** DONE — 1 attempt, full track, branch feat/evals-batch2, commit 64218dd
- **What happened:** Root cause: meta.yaml missing `multi_turn: true` → runs used --output-format json (one-shot) → bare rung1 timed out at 300s with 0 events. Fix: added `multi_turn: true` + `timeout_sec: 900`. Two-sided check.sh validation run: PASS on cf84a6b (real acwr_7_28), FAIL on chronic÷acute inversion. STATUS updated in meta.yaml and CONTRACT-NOTE.md.
- **What worked:** Read analyze-report for root cause, then direct implementation. check.sh already worked correctly; the harness plumbing was the bug.
- **What failed:** None — single attempt converged.
- **Remember next run:** When a multi_turn task is missing `multi_turn: true` in meta.yaml, ALL rungs run as one-shot JSON (num_events always 0). The 0-event symptom is a meta.yaml parsing bug, not a streaming bug. Check meta.yaml before debugging the harness.

## 2026-07-15 — dev-team-auto — Item 2: Wire Opus spot check by default
- **Outcome:** DONE — 1 attempt, light track, branch feat/evals-batch2, commit 64218dd
- **What happened:** OPUS_SPOTCHECK flag existed (added in 48d7d20) but defaulted to 0. Changed default to 1 and renamed the opt-in flag to an opt-out --no-opus-spotcheck. Comment updated to reflect new default.
- **What worked:** Single-line change + usage comment update. All downstream plumbing (run_matrix.py model loop, stats.py cross_model_section) already handled multiple models correctly.
- **What failed:** None.
- **Remember next run:** The Opus spot check plumbing was always there — the only missing piece was the default. If cross_model_section ever shows "opus=none" again, first check whether OPUS_SPOTCHECK reverted to 0 or --no-opus-spotcheck was passed.

## 2026-07-15 — dev-team-auto — Item 3: No-signal warning in stats.py
- **Outcome:** DONE — 1 attempt, light track, branch feat/evals-batch2, commit 64218dd
- **What happened:** Added no-signal detection at top of verdict_section() body. Computed inline from scores without adding a parameter to the function. Warning appears as first content line when every rung-pair is a tie across all models.
- **What worked:** Inline computation (no signature change). The logic mirrors sign_test() — check if any task flips between two rungs for any model.
- **What failed:** None.
- **Remember next run:** The verdict_section() `data` parameter is UNUSED in the current implementation (the function only uses `scores`). If adding features, note this and consider whether to clean it up.

## 2026-07-15 — dev-team-auto — Item 4: Draft discriminating tasks
- **Outcome:** DONE — 1 attempt, light track, branch feat/evals-batch2, commit 64218dd
- **What happened:** Created 3 NEEDS-VALIDATION drafts in tasks/_draft/knowledge/: memory-notes-format (rung3 — one-file-per-doc convention vs generic advice), claude-md-comment-gate (rung2 — no-WHAT-comments policy vs document-your-code default), memory-tradeoffs-reflex (rung3 — proactive tradeoffs reflex; highest risk of being non-discriminating). REVIEW.md with validation instructions included.
- **What worked:** Targeting preferences that are counter-intuitive vs general best practices (most reliable discrimination). Flagging the highest-risk draft explicitly.
- **What failed:** None in authoring; validation not done (NEEDS-VALIDATION by design).
- **Remember next run:** Draft 3 (memory-tradeoffs-reflex) has explicit warning that modern Claude models may already volunteer tradeoffs — validate rung1 behavior before trusting this one. If it doesn't discriminate, cut it. Draft 1 and 2 are higher-confidence discriminators.
