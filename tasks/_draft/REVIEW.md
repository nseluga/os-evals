# Hard-task batch #1 — review proposal (APPROVAL-GATED)

Two draft tasks for the harder rung-4 suite, one per orchestrator. **Nothing here is in the
live suite** — everything lives under `tasks/_draft/`, and `find_tasks()` skips any path
segment starting with `_`, so these are invisible to the scored matrix until you approve
and a later step moves them into the real tree.

Batch coverage of the three quality dimensions the step asked for:

| Task | Orchestrator | Quality dimension(s) enforced | Also checks |
|------|--------------|-------------------------------|-------------|
| A. `pathguard-resolver` | `dev-team` (multi-step) | **security** (traversal, absolute/NUL validation, symlink escape, sibling-prefix bypass, no shell-out) | functional correctness |
| B. `rangestats-engine` | `dev-team-auto` (multi-turn, PLAN.md) | **performance** (time bound) + **scalability** (sub-quadratic at 4× size) | correctness vs oracle, input validation |

Both: `contaminated: false`, `group: clean`, stdlib-only (no setup.sh/venv/network),
`multi_turn: true`, headless-safe pure unit/perf/filesystem checks reading `$WORKSPACE_DIR`.
Exit convention 0=pass / 1=task failure / 2=infra.

---

## Task A — `pathguard-resolver`  (dev-team, security + correctness)

**What it probes.** Build a small multi-file package (`src/pathguard/errors.py` +
`resolver.py`) that resolves an *untrusted* client path inside a fixed base directory and
refuses every escape. This is the shape `dev-team` is built for: multi-file, subtle
correctness, a real QA loop (Engineer builds → QA runs the attack battery → Optimization
Reviewer flags the containment logic → Bug Fixer applies findings → repeat).

**Quality dimension the check enforces — security.** `check.sh` runs a vendored
`test_pathguard.py` (copied in at check time so the model can't edit it) that fires an
attack battery: `../` traversal, absolute path, NUL byte, a symlink inside the base
pointing outside, and the **sibling-prefix bypass** (base `/x/data` vs target
`/x/data-evil`). It also greps the source for `os.system`/`subprocess`/`eval`/`exec` to
assert the resolver never shells out. Functional correctness is checked too (normal nested
paths resolve, not-yet-created files under base are allowed, `""`/`"."`/`"./"` → base).

**Why it's hard enough to fail bare Claude.** The naive one-shot solution
(`os.path.normpath(os.path.join(base, user))` + `str.startswith(base)`) passes the happy
path and simple `../` cases but is bypassable two ways the check specifically probes:
(1) `normpath` does **not** follow symlinks, so a symlink component escapes undetected —
you need `os.path.realpath`; and (2) `startswith` treats `/x/data-evil` as inside
`/x/data`. The correct solution needs `realpath` + `os.path.commonpath`, plus splitting
`PathValidationError` (malformed input) from `PathSecurityError` (escape). Non-obvious to
get fully right in a single pass.

**Contamination call — clean.** Path-traversal defense is general CS; nothing about it
lives in Nate's `~/os` project READMEs or library notes. Any capable model can solve it
from the prompt alone — the eval measures whether dev-team's QA loop reaches the correct
containment logic *more reliably* than a bare one-shot, not whether the scaffold leaks the
answer.

**Two-sided validation evidence.**

- Reference GOOD (`realpath` + `commonpath`):
  `WORKSPACE_DIR=.../pg_good bash check.sh` → **rc=0**, all 13 checks PASS incl. symlink +
  sibling-prefix escapes → `ALL CHECKS PASSED`.
- Reference BAD (`join` + `normpath` + `startswith`):
  `WORKSPACE_DIR=.../pg_bad bash check.sh` → **rc=1**. It passes every happy-path,
  validation, and simple-traversal check but FAILS exactly the two subtle escapes:
  ```
  FAIL sibling-prefix escape -> PathSecurityError (... returned '.../pg_base_xxx-evil/secret.txt')
  FAIL symlink component escaping base -> PathSecurityError (... returned '.../escape/anything.txt')
  ```
  → the check discriminates on the *security* logic, not a trivial bug.

---

## Task B — `rangestats-engine`  (dev-team-auto, performance + scalability)

**What it probes.** Build an online statistics engine `LiveStats`
(`record` / `count_below` / `sum_below`) over an interleaved integer score stream
(`[0, 1_000_000]`). The seed ships a **`PLAN.md`** (Items 1–3, ending with a
`⚠️ AUTONOMOUS RUN — STOP HERE` marker) plus `PROGRESS.md`; `dev-team-auto` reads the plan
top to bottom, drives each item through its convergence loop, and updates PROGRESS after
each. `timeout_sec: 1800`.

**Quality dimensions the check enforces — performance + scalability.** `check.sh` runs a
vendored `test_rangestats.py` with three gates: (1) **correctness** — interleaved
record/query vs a brute-force oracle, plus boundaries and input validation; (2)
**performance** — a 200k-op interleaved workload must finish under a 15s `SIGALRM` budget
(a too-slow design is interrupted and fails fast, so the check itself stays bounded); (3)
**scalability** — elapsed at 4× the size must grow sub-quadratically (ratio < 8;
linearithmic ≈ 4×, quadratic ≈ 16×).

**Why it's hard enough to fail bare Claude.** Records and queries **interleave** (online),
so you can't batch or pre-sort. Every tempting quick solution blows the bound: a list +
per-query scan is O(N) per query → O(N²); `bisect.insort` into a sorted list is O(N) per
insert (list shift); a numpy `(arr < q).sum()` is O(N) per query and can't be batched
online. The intended solution is a **Fenwick / binary-indexed tree** keyed on the value
domain (two parallel trees, one for count one for sum) → O(log domain) per op. A bare
one-shot frequently ships the O(N) rescan that *passes on small input and dies under
load* — precisely the failure mode dev-team-auto's QA+review loop exists to catch.

**Contamination call — clean.** Order-statistics over a bounded integer domain is standard
CS; nothing about it lives in `~/os`.

**Two-sided validation evidence.**

- Reference GOOD (dual Fenwick tree):
  `WORKSPACE_DIR=.../rs_good bash check.sh` → **rc=0**, all 13 checks PASS →
  `performance: 200000 interleaved ops under 15.0s (elapsed=0.48s)` and
  `scalability: ... (ratio=3.7, small=0.122s big=0.453s, want <8)` → `ALL CHECKS PASSED`.
- Reference BAD (list + per-query scan):
  `WORKSPACE_DIR=.../rs_bad bash check.sh` → **rc=1** (≈45s wall, alarms fire). It PASSES
  all 11 correctness + validation checks, then FAILS exactly the quality gates:
  ```
  FAIL performance: 200000 ops did NOT finish within 15.0s (O(N)-per-query?)
  FAIL scalability: 4x-size run did not complete (too slow / quadratic)
  ```
  → the check discriminates on *performance/scalability*, not correctness.

---

## Setup-flattering audit (what you asked me to watch for)

Neither check rewards the mere presence of the `~/os` scaffold:

- Both are pure behavioral tests (an attack battery; a perf/scalability harness) authored
  independently of any `~/os` content. `grep -rniE 'pathguard|traversal|fenwick|LiveStats|
  count_below'` over `~/os` is empty — the answers are not pre-recorded anywhere in the
  setup, so rung 2 (CLAUDE.md/knowledge) gets no free lift.
- The vendored test is copied in at check time, so the model cannot edit or peek-and-hardcode
  against it.
- The gates measure *genuine task success* (does the resolver actually contain? does the
  engine actually stay sub-linear?), which is exactly the delta the eval wants to detect —
  the legitimate opposite of a scaffold-reward check.
- Residual note (A): the check greps the model's source for `subprocess`/`eval`/etc. That's
  a security assertion (no shell-out with untrusted input), spec-compliant, not scaffold
  reward. Residual note (B): the 15s perf budget is machine-dependent, but the good/naive
  gap is ~100× (0.48s vs. never-finishes), so the bound separates them with large margin on
  any plausible runner.

## Reproduce the validation

```bash
# from the repo root; reference solutions are staged in the job tmp dir during authoring.
# (Re-create them from REVIEW's descriptions, or ask me to re-run.)
WORKSPACE_DIR=<good_ws> bash tasks/_draft/coding/pathguard-resolver/check.sh </dev/null   # -> rc 0
WORKSPACE_DIR=<bad_ws>  bash tasks/_draft/coding/pathguard-resolver/check.sh </dev/null   # -> rc 1
WORKSPACE_DIR=<good_ws> bash tasks/_draft/coding/rangestats-engine/check.sh </dev/null    # -> rc 0
WORKSPACE_DIR=<bad_ws>  bash tasks/_draft/coding/rangestats-engine/check.sh </dev/null    # -> rc 1
```

## Decision

Approve either/both to promote into the live tree (a later step moves them out of
`tasks/_draft/` and wires `curated_skill` into the scored matrix), or reject with notes.
Nothing counts until you sign off on each check.

---

# Knowledge-layer draft tasks — batch #3 (APPROVAL-GATED, 2026-07-15)

Three candidate discriminating tasks targeting rung2/rung3/rung4 layers with zero
demonstrated lift in iterations 3–4. **Nothing here is in the live suite.**

All are marked `STATUS: NEEDS-VALIDATION` in their meta.yaml; none will be scored
until you approve and promote them.

## Why these exist

Iteration 4 Sonnet arm at ceiling (near-all ties). The only tasks with lift are
`memory-notes-format` (rung3) and `claude-md-comment-gate` (rung2), both now live.
Need more tasks that discriminate at the rung boundaries with zero current signal.

The batch targets:
- Skill-specific knowledge (rung4): exact formats the dt-qa and dt-review skills use
- Memory-specific preference (rung3): terse response policy (counter-training-data)

| Task | Layer | Target knowledge | Risk |
|------|-------|-----------------|------|
| `dt-qa-verdict-format` | rung4 | VERDICT: PASS/FAIL exact format; gate mode distinction | low-medium |
| `dt-review-severity-policy` | rung4 | Critical/Important blocks; Minor applied without re-QA | low |
| `memory-terse-response-policy` | rung2/3 | No trailing summaries when diffs/output visible | medium |

---

## Task 1 — `dt-qa-verdict-format` (rung4, dt-qa skill)

**What it probes.** When the dt-qa agent finishes evaluating a plan item, it must emit
`VERDICT: PASS` or `VERDICT: FAIL` on its own line — machine-readable format the
orchestrator routes on. It must also know that `tests+behavioral` gate mode requires
running the live path (smoke pass against a real server), not just tests.

**Discrimination hypothesis.** Without reading `~/.claude/skills/dt-qa/skill.md`, a model
gives generic "tests pass/fail" or "all checks green" language. The VERDICT prefix is
system-specific and counter-intuitive vs CI output formats.

**Check.** Requires both: (1) `VERDICT: PASS` / `VERDICT: FAIL` string pattern, and (2)
description of `tests+behavioral` as requiring behavioral/smoke/live/endpoint exercise.

**Validation concern: low-medium.** The VERDICT format is unique to this system. The
gate mode distinction is documented only in the skill files.

---

## Task 2 — `dt-review-severity-policy` (rung4, dt-review skill)

**What it probes.** The convergence loop's severity policy: Critical AND Important
findings block exit and consume an attempt (require another QA pass); Minor findings
are applied by dt-fix once without looping. This split is specific to the loop spec.

**Discrimination hypothesis.** Most code review workflows require ALL issues fixed
before merge. Nate's loop deliberately allows Minor to pass without re-QA — this is
counter-intuitive and requires reading `convergence-loop.md`. Bare Claude says
"fix everything before shipping."

**Check.** Requires: (1) Critical mentioned as blocking, (2) Important mentioned as
blocking, (3) Minor mentioned as non-blocking (applied without QA loop).

**Validation concern: low.** The Critical/Important vs Minor split with Minor
explicitly not requiring re-QA is very specific to this system.

---

## Task 3 — `memory-terse-response-policy` (rung2/rung3)

**What it probes.** Nate's memory and CLAUDE.md say: do not add trailing summaries
("I've completed..."), do not narrate steps taken. When the user can see diffs/tool
output, a closing summary is redundant. Bare Claude almost always adds a polite summary.

**Discrimination hypothesis.** LLM training strongly pushes toward polite summaries
and completion acknowledgements. CLAUDE.md + memory explicitly invert this. Counter-
training-data preferences are the highest-confidence discriminators.

**Check.** Scenario: should you end a response with "Here's what changed: I added X,
modified Y..."? Pass if response says no/skip/omit. Fail if it recommends the summary.

**Validation concern: medium.** Claude 4.x may already be trained toward conciseness.
Validate rung1 explicitly — if bare Claude already says skip the summary, redesign.

---

## Validation process for batch #3

For each task, before promoting:
1. `./run.sh --tasks _draft/knowledge/TASKNAME --rungs 1 --no-opus-spotcheck` (bare rung1)
2. Verify check.sh FAILS on the rung1 output (the task discriminates)
3. `./run.sh --tasks _draft/knowledge/TASKNAME --rungs 4 --no-opus-spotcheck` (skills rung4)
4. Verify check.sh PASSES on the rung4 output
5. Move into `tasks/knowledge/TASKNAME/` and register `curated_skill` in meta.yaml

Do NOT promote until both sides confirmed.
