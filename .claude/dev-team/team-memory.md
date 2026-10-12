# Dev-team memory log

## Standing notes

Distilled from the 2026-07-13 and 2026-07-15 (batch 2) entries and the batch-3 notes; each re-verified against main on 2026-10-12.

**Harness parsing and filtering**
- `run_matrix.py` and `score.py` each have their own `read_task_meta`; any meta.yaml parsing change goes in both. The critical safety check is the column-0 guard (`if line[:1] in (" ", "\t"): continue`), so indented prose like "sentinel: true" inside a description can't misclassify a task.
- A new filter helper (`_effective_scores`, `_is_sentinel`) must be applied at every site that builds a score table. `cross_model_section` is a separate code path from `render_markdown` and was missed once. Grep for the unfiltered `scores` / `all_scores` variable before calling a filtering change done.
- `verdict_section(data, scores)` never uses `data`; only `scores` is used. Consider cleaning it up if you touch the function.
- Any new `_meta` detection field needs a fallback in `score.py` so re-scoring old transcripts works. `rate_limited` is the model: use the stamped flag if present, else detect inline from the result text.
- The rate-limit retry loop in `run_one()` re-parses the transcript on every attempt. This is intentional, because the parse is how it detects 429. `events` is rebuilt fresh by `_parse_stream` each time.
- `run.sh` builds paths from `$RUNS_DIR` (and `$TASKS_DIR`, `$CONFIGS_DIR`, `$SCORECARDS_DIR`). Add cleanup with those variables, not hardcoded `runs/`.

**Eval behavior and scoring**
- A multi_turn task without `multi_turn: true` in meta.yaml runs every rung as one-shot JSON, so `num_events` is always 0. That symptom is a meta.yaml bug, not a streaming bug. Check meta.yaml first.
- Opus spot check is on by default (`OPUS_SPOTCHECK=1`; opt out with `--no-opus-spotcheck`). If `cross_model_section` shows `opus=none`, check for the opt-out flag or a reverted default before debugging plumbing.
- Re-scoring old transcripts cannot give real pass/fail for coding tasks that need a workspace. `run.sh` deletes `runs/*.ws` after scoring (unless `--keep-ws`), so `pir-workload-feature` shows all `WORKSPACE_DIR` infra on re-score. Only the original score has real results.
- `pir-workload-feature`: `check.sh` is deterministic (5/5 PASS on the correct impl, 5/5 FAIL on the inverted ratio; CONTRACT-NOTE.md section D). The rung4 `skill_fired=False` is a routing/config failure, not evidence against `baseball-research`. Do NOT prune `baseball-research` on iter-4 data. On main, rung 4's `CURATED_SKILLS` (`harness/build_configs.sh`) is only dev-team, dev-team-auto and dt-* skills. `baseball-research` is not loaded, so it can never fire there even though the task's meta.yaml names it as `curated_skill`. The routing fixes (`8bc292b` explicit skill invoke at rung 4, `dd7b371` quarantine routing failures in the scorecard, `9816b21` detect skill_fired for single-turn tasks, `2937cce` auth-detector false positives) exist only on branch `worktree-rung4-skill-directive`, not on main.

**Task authoring**
- PLAN.md test specs can be illustrative rather than literal. Read the actual implementation before writing tests (e.g. the auth patterns are `authentication_error` / `unauthorized`, not "Authentication" / "403").
- Best discriminators are preferences that run counter to general best practice, or system-specific formats. Validate rung1 before trusting a draft. Bare Claude already volunteers tradeoffs, so `memory-tradeoffs-reflex` was cut for being non-discriminating.
- `memory-terse-response-policy` is still a NEEDS-VALIDATION draft in `tasks/_draft/knowledge/`. Medium risk: Claude 4.x may already be terse at rung1, so validate rung1 first.
- Live in `tasks/knowledge/`: `memory-notes-format`, `claude-md-comment-gate`, `dt-qa-verdict-format`, `dt-review-severity-policy`. `tasks/_draft/knowledge/` still holds stale NEEDS-VALIDATION copies of the last two; the live copies are authoritative. `tasks/knowledge/claude-md-comment-gate/meta.yaml` still says `STATUS: NEEDS-VALIDATION` although it was validated. The validation process is in `tasks/_draft/knowledge/REVIEW.md` (the older `tasks/_draft/REVIEW.md` covers hard-task batch #1).

**Process**
- Make each item's edits in that item's worktree, never the main checkout, which tracks a different branch and won't be merged. Check `git worktree list` and the current branch first.

## Recent runs

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
