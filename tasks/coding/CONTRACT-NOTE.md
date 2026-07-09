# Coding batch — contract note + setup-flattering audit

Read this before approving the 3 coding tasks. It covers (A) a contract change the
coding checks require, and (B) the per-check audit for setup-flattering bias.

## A. The proven contract does NOT support coding checks yet — STOP-and-tell

The smoke-tested contract (branch `worktree-proof-of-mechanism`) does exactly this:
- `run_matrix.py` pipes `prompt.md` into `claude -p` with **no workspace / no cwd**.
- `score.py` runs `check.sh` with **only the transcript JSON on stdin** — no filesystem.
- `print-date/check.sh` therefore greps the final `result` text. That is the whole contract.

Every real coding task modifies files, so a text-only check cannot score it. To keep
faith with "fit the proven contract or stop and tell you" — I stopped. All three checks
are written against a **minimal proposed extension**, not silently wired in:

1. `run_matrix.py`: for a task with a `workspace.ref`, materialize the frozen state
   (git archive of the SHA, or the tarball) into a per-run temp dir, provision deps if
   the task needs them (`npm ci`, `python -m venv`), and run `claude -p` with that dir
   as **cwd**.
2. `score.py`: pass that dir to `check.sh` as the **`WORKSPACE_DIR`** env var.
3. Checks still receive the transcript on stdin (they `cat >/dev/null` it) so the
   text-only contract is a strict subset — `print-date` keeps working unchanged.

This is additive and backward-compatible. **I have not modified the harness.** If you
approve the tasks, approving this extension is the prerequisite; if you'd rather shape
it differently (e.g., check runs inside the sandbox, or a `check(workspace, transcript)`
Python signature instead of a shell env var), say so and I'll rewrite the checks to match.

Each check exits `2` (not `1`) when `WORKSPACE_DIR` is unset — an infra error distinct
from a task failure, so a missing extension can never masquerade as a passing/failing run.

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

### 2. dashboard-inbox — clean — LOW risk, one adjacency to watch ⚠️
- Check = the repo's OWN behavioral test (`inbox-ui.test.ts`, vendored so the model
  can't edit it). Rewards a correct implementation, not scaffold presence.
- Adjacency to watch: the PLAN item references `~/portfolio/STANDARDS.md` for *style*.
  The test checks *behavior*, not style, so passing does not require those docs — but a
  rung-4 run could still "feel" advantaged. Flagged, not a contamination.
- STATUS: NEEDS-VALIDATION — I have not yet dry-run the vendored test against the real
  solution commit (c8dee19/10db84a) from base 5a4c800 to confirm it's an achievable gate.

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
  (b) I authored the test, so I control the gate — higher scrutiny warranted;
  (c) STATUS: NEEDS-VALIDATION — I must confirm the base cf84a6b^ ships the rolling-window
  helpers (so the task really is "add ACWR," not "build the module"), that the check
  passes the real cf84a6b implementation, and that it fails an inverted/leaky one.

## C. Open questions for you
1. Approve the `WORKSPACE_DIR` contract extension (Section A), or reshape it?
2. Two of three tasks are from project-dashboard. Acceptable for representativeness, or
   swap one for a Patio task? (Patio's backend is Flask+Supabase — network deps make
   headless checks much harder, which is why I leaned on project-dashboard.)
3. OK to spend a validation pass running tasks 2 & 3 checks against their real solution
   commits before you rely on them? (Recommended — removes the NEEDS-VALIDATION flags.)
