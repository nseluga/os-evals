# Coding batch — contract note + setup-flattering audit

Read this before approving the 3 coding tasks. It covers (A) a contract change the
coding checks require, and (B) the per-check audit for setup-flattering bias.

## A. WORKSPACE_DIR extension — IMPLEMENTED (you approved the shape)

The smoke-tested contract only supported text checks: `run_matrix.py` piped `prompt.md`
into `claude -p` with no cwd, and `score.py` gave `check.sh` only the transcript. Real
coding tasks modify files, so that can't score them. You approved the extension shape
(env-var + shell check, per-task `setup.sh`); it is now wired into the harness on this
branch, additively and backward-compatibly:

1. `run_matrix.py` — for a task with a `workspace.ref`, `restore_workspace()` parses its
   `origin:`/`sha:`, does `git archive <sha> | tar -x` into a persisted per-run dir
   (`runs/<run_id>.ws`), runs the task's optional `setup.sh` there (deps: `npm ci` /
   `venv`), then runs `claude -p` with that dir as **cwd**. The dir is recorded in
   `_meta.workspace_dir`.
2. `score.py` — reads `_meta.workspace_dir` and passes it to `check.sh` as **`WORKSPACE_DIR`**.
3. Checks still drain the transcript on stdin, so the old text-only contract is a strict
   subset — `print-date` runs unchanged. `find_tasks` now also discovers category-grouped
   tasks (`tasks/coding/<name>`), not just flat ones.

Each check exits `2` (not `1`) when `WORKSPACE_DIR` is unset — an infra error distinct
from a task failure, so a missing/broken restore can never masquerade as a real verdict.

Open follow-ups (not blocking approval): (a) `runs/*.ws` dirs are persisted for scoring
and should be cleaned by `run.sh` after `score.py`; (b) `npm ci`/venv per run adds time —
we can cache a warm `node_modules`/`.venv` and copy it in if the 48-run matrix gets slow.

## B. Setup-flattering audit (what you asked me to flag)

Definition I used: a check is **setup-flattering** if it rewards the *presence of the
~/os scaffold* (CLAUDE.md / memory / skills) rather than *genuine task success*. The
legitimate opposite is a check that measures real success, even if the scaffold happens
to help achieve it — that delta is exactly what the eval wants to detect.

### 1. launchd-service — clean — LOW risk ✅
- Check = filesystem assertions on the plist + scripts. Validated: PASSES the real
  solution (exit 0), FAILS a wrong `npm run dev` plist (exit 1). It discriminates.
- Not setup-flattering: nothing in it references ~/os, skills, or memory. `grep -rniE
  'launchd|plist'` over the project's docs is empty, so the answer is not pre-recorded
  anywhere in the setup. A bare Claude with the prompt alone can pass.
- Residual nit: asserts the exact log paths `/tmp/project-dashboard.*`. Those are given
  verbatim in the prompt, so that's spec-compliance, not scaffold-reward.

### 2. dashboard-digest — clean — LOW risk, one adjacency to watch ✅
- (Swapped from dashboard-inbox during the validation pass: the inbox test turned out to
  be a LIVE integration test needing a running dev server — a bad fit for a headless
  one-shot. Item 3.1's digest test is a PURE unit test, so I moved to it. Same repo, same
  spirit, cleaner gate.)
- Check = the repo's OWN pure unit test (`digest.test.ts` on `computeDigestBuckets`,
  vendored so the model can't edit it). Explicit boundary cases (<=7 vs 8 days, overdue
  exclusion, missing due_date). Rewards a correct implementation, not scaffold presence.
- Adjacency to watch: the PLAN item references `~/portfolio/STANDARDS.md` for *style*.
  The test checks *behavior*, not style, so passing does not require those docs. Flagged,
  not a contamination.
- STATUS: VALIDATED — real `digest.ts` (from 5a4c800) passes 19/19; breaking the `<=7`
  boundary to `<7` fails the boundary test as expected. Fair, achievable gate.

### 3. pir-workload-feature — knowledge-informed / contaminated — HIGHEST risk, mitigated ⚠️⚠️
- This is the batch's deliberate contaminated task, and the sharpest audit case.
- The trap I actively avoided: asserting Nate's idiosyncratic ACWR formula
  (`pitches_7d / (pitches_28d/4).clip(lower=1)`, rounded 4). A check demanding those exact
  constants would reward reproducing a repo-specific choice recorded in the code/README —
  i.e., setup-flattering. Instead the check is **property-based and convention-agnostic**:
  finite output, current-appearance exclusion (no leakage), and monotonicity in acute load.
  These are true of *any* correct ACWR, so the check rewards domain correctness, not
  memorized constants.
- Where the legitimate knowledge delta lives: knowing ACWR semantics (acute÷chronic,
  exclude the current game). The baseball-research skill (rung 4) supplies this; a bare
  Claude may invert the ratio or leak the current game and fail. That is the eval working
  as intended — not flattery — because the check is a real behavioral test.
- Honest caveats: (a) sourced from git, not session history (PIR sessions are thin);
  (b) I authored the test, so I control the gate — higher scrutiny warranted.
- STATUS: VALIDATED (2026-07-15: two-sided confirmed by dev-team-auto)
  - PASS: `git archive cf84a6b` (real acwr_7_28 implementation) → all 3 properties pass
  - FAIL: inverted ratio (chronic÷acute) → Property 2 fails with "first appearance acwr=1.0
    too high" (check correctly rejects wrong direction / division-order errors)
  - base cf84a6b^ ships rolling helpers but not `acwr_7_28` (task really is "add ACWR",
    119 lines vs 200 at HEAD); check is convention-agnostic (property-based, not constant-checking)

## C. Status / remaining question
- ✅ WORKSPACE_DIR extension implemented (Section A) — approved shape.
- ✅ Validation pass done — all three checks pass their real solutions and fail broken
  ones (launchd: npm-plist; digest: broken boundary; pir: inverted ratio).
- ⚠️ Still open: two of three tasks are project-dashboard. Acceptable for representativeness,
  or swap one for a Patio task? (Patio's backend is Flask+Supabase — network deps make
  headless checks much harder, which is why I leaned on project-dashboard. My
  recommendation: keep as-is for the coding batch and get Patio coverage in the analysis
  batch instead.)

## D. pir-workload-feature determinism + skill_fired audit (2026-07-15, batch 3)

Item 4 of PLAN.md batch 3 directed a determinism re-validation and inspection of the
`_meta.skill_fired` field for the failing r3/r4 runs.

### Determinism result

check.sh run 5 times on each fixed input from a fresh restored workspace (base cf84a6b^
+ venv):

- **Known-correct** (cf84a6b impl with acwr_7_28): **5/5 PASS** — output identical across
  all 5 runs; no timing or ordering flakiness.
- **Known-wrong** (inverted ratio chronic÷acute): **5/5 FAIL** — consistently fails at
  Property 1 (acwr contains inf/NaN when pitches_7d=0 in acute window and chronic is
  nonzero, so inversion produces inf). Result is deterministic.

**Conclusion: check.sh is deterministic on fixed inputs.** The r3/r4 instability is NOT
a check flakiness issue.

### skill_fired audit

Inspected `_meta.skill_fired` for all iter-4 pir-workload-feature Sonnet runs:

- **rung1 r1–r3:** `skill_fired=False` (expected — no skills at rung1)
- **rung2 r1–r3:** `skill_fired=False` (expected — no skills at rung2)
- **rung3 r1–r3:** `skill_fired=False` (expected — no skills at rung3)
- **rung4 r1–r3:** `skill_fired=False` ← **ROUTING FAILURE**

All 3 rung4 repeats had `skill_fired=False` — the `baseball-research` skill was never
invoked, even though it was available. The r3→r4 regression (r2: 3/3, r3: 1/3, r4: 1/3
in original scorecard) is a **routing failure**, not evidence that the skill caused the
regression. The model at rung4 attempted the task without invoking baseball-research.

**Call per PLAN item 4:** Routing failure — NOT a confirmed `baseball-research` prune
candidate. The skill never triggered, so we have no signal about what the skill would
have done. The instability is attributed to the model failing to route correctly to the
skill at rung4. Do NOT prune baseball-research based on iter-4 data.

### What remains noisy

The original r1 2/3 vs r2 3/3 result is NOT from this workspace (iter4 Sonnet workspace
dirs were cleaned up before re-score). The r3/r4 failure with WORKSPACE_DIR infra in
re-score confirms check.sh ran at original score time (workspaces existed). The per-run
`is_error=False` for all Sonnet pir runs confirms the model produced output — the
check.sh gate is what determines pass/fail, and it is now confirmed deterministic.
