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

## 2026-07-15 16:00 — dev-team-auto — Item 1: Classify 429 rate limits as infra, not task fails
- **Outcome:** DONE — 1 attempt, light track, branch feat/harness-batch3, commit c345118
- **What happened:** Added looks_like_rate_limit() + _RATE_LIMIT_PATTERNS in run_matrix.py; wired rate_limited into _meta; score.py short-circuits before run_check when rate_limited (same pattern as auth_error). 5 new tests, all pass.
- **What worked:** Mirroring the auth_error pattern exactly — same structure, same check_rc==2 path.
- **What failed:** None.
- **Remember next run:** Old transcripts (pre-batch3) don't have rate_limited in _meta. score.py handles this via inline detection from result text (rate_limited = meta["rate_limited"] if "rate_limited" in meta else inline check). Any future _meta field added for detection should also have a fallback in score.py for re-scoring existing runs.

## 2026-07-15 16:15 — dev-team-auto — Item 2: Retry rate-limited runs with bounded backoff
- **Outcome:** DONE — 1 attempt, full track, branch feat/harness-batch3, commit a3e1921
- **What happened:** Added RATE_LIMIT_MAX_RETRIES=3, rate_limit_backoff_seconds(attempt) → 30s/60s/120s±20%, retry loop in run_one() wrapping the subprocess call. Loop exits on success, auth_error, or timeout. 8 new tests.
- **What worked:** Wrapping the subprocess block in a for loop with `break` at success or non-retryable condition; `continue` on 429. Clean logic.
- **What failed:** None.
- **Remember next run:** The retry loop re-parses the transcript on each attempt (needed to detect rate limit). This is intentional — parse after each attempt, not once at the end. The `events` list from multi-turn runs should be reset between attempts (it is, since _parse_stream is called fresh each time).

## 2026-07-15 16:30 — dev-team-auto — Item 3: Re-score iteration 4's existing transcripts
- **Outcome:** DONE — trivial track, branch feat/harness-batch3, commit 8d7db5c
- **What happened:** Re-ran score.py over existing runs/ dir. 28 Opus 429 runs now infra_error=True. Cross-model comparison shows real data (Opus r1 3/13 from analysis tasks that actually ran). Saved as scorecards/20260715T151129Z-483c1d0-rescored.{md,scores.json}.
- **What worked:** Inline rate-limit detection in score.py (fallback for old transcripts without _meta.rate_limited).
- **What failed:** Old transcripts had auth_error=False and no rate_limited field — needed the inline detection fallback. This was discovered during re-score.
- **Remember next run:** pir-workload-feature Sonnet runs show WORKSPACE_DIR infra in re-score — the workspace dirs are cleaned up and check.sh can't run. Re-scoring coding tasks with workspace requirements always shows infra_error. Only original score (with live ws dirs) gives real pass/fail for those tasks. Don't be confused by all-infra pir results in re-scored data.

## 2026-07-15 16:45 — dev-team-auto — Item 4: Make pir-workload-feature deterministic or mark it noisy
- **Outcome:** DONE — light track, branch feat/harness-batch3, commit 800d5f9
- **What happened:** Restored fresh workspace from cf84a6b^. Ran check.sh 5 times on correct impl (5/5 PASS) and wrong impl (5/5 FAIL). Inspected _meta.skill_fired for all iter-4 pir Sonnet runs: skill_fired=False at ALL rungs including rung4. Results recorded in tasks/coding/CONTRACT-NOTE.md section D.
- **What worked:** Fresh workspace restore + 5-run determinism check. skill_fired field already present in transcripts.
- **What failed:** None.
- **Remember next run:** baseball-research skill never fired at rung4 in iter4 (skill_fired=False all 3 repeats). The r2→r3/r4 regression is a routing failure, NOT evidence against the skill. Do NOT prune baseball-research based on iter-4 data. Next session should investigate WHY routing fails at rung4 — is the skill path config wrong? Does the prompt need to mention baseball research more explicitly?

## 2026-07-15 17:00 — dev-team-auto — Item 5: Draft candidate discriminating tasks
- **Outcome:** DONE — light track, branch feat/harness-batch3, commit 9f07c76
- **What happened:** Created 3 NEEDS-VALIDATION drafts in tasks/_draft/knowledge/: dt-qa-verdict-format (rung4 — VERDICT: PASS/FAIL format and gate mode distinction), dt-review-severity-policy (rung4 — Critical/Important blocks vs Minor non-blocking), memory-terse-response-policy (rung3 — no trailing summaries). Verified 0 drafts in scored matrix (17 scored tasks unchanged). REVIEW.md updated.
- **What worked:** Targeting system-specific formats (VERDICT:) and counter-intuitive rules (Minor doesn't re-loop; no trailing summaries). These are the highest-confidence discriminators.
- **What failed:** None in authoring.
- **Remember next run:** dt-review-severity-policy has high discrimination confidence (low risk) because the Minor-doesn't-re-loop policy is very counter-intuitive vs standard code review. memory-terse-response-policy has medium risk — validate rung1 first; Claude 4.x may already be terse. Validation process documented in tasks/_draft/REVIEW.md.
