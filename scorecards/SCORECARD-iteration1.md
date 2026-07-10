# Scorecard — Is the ~/os setup helping? (Iteration 1)

**Bottom line, in plain English:** On these 12 objective tasks, the ~/os setup barely
changes whether Claude *succeeds* — because a capable base model (Sonnet 4.6) already
passes most of them bare. Bare Claude passed 8/12; the full setup passed 10/12. The only
two tasks the setup flipped from fail→pass were **writing tasks driven by knowing your
voice and project context**, and that win came entirely from the **CLAUDE.md / knowledge
layer (rung 2)** — not from memory, and not from any skill. Every one of the 8 curated
skills that had a dedicated task was on a task the bare model *already* passed, so no
skill changed a pass/fail outcome. And the wins that CLAUDE.md did produce **disappear on
a stronger model**: bare Opus passes those same two tasks with no setup at all.

So: **the knowledge layer earns its keep cheaply; memory and the curated skills did not
show measurable pass/fail value on this suite — but that's partly because the suite is too
easy and pass/fail is the wrong lens for what skills do.** The honest headline is "this
iteration can't yet justify the skills," not "the skills are useless." See caveats.

---

## The numbers

**Sonnet 4.6 ladder (48 runs, 12 tasks × 4 rungs):**

| Rung | What's added | Passed | Avg tokens |
|------|--------------|--------|-----------|
| 1 | bare Claude | 8/12 | 71k* |
| 2 | + CLAUDE.md / knowledge routing | **10/12** | 63k |
| 3 | + memory (behavior instructions) | 9/12 | 66k |
| 4 | + curated skills | 10/12 | **137k** |

\*rung-1 average is inflated by the two heavy coding tasks + a retry; the meaningful token
story is **rung 4 costs ~2× the tokens of rungs 2–3** for no extra passes.

**What each added layer bought (fail→pass flips, Sonnet):**
- **CLAUDE.md (rung1→2): net +2** — `plain-explainer`, `portfolio-writeup`. The one layer with real, attributable lift.
- **Memory (rung2→3): net −1** — one noisy regression, zero gains.
- **Curated skills (rung3→4): net +1** — and that single flip (`portfolio-writeup`) is a soft-check recovery within noise, not a skill doing its job.
- **Full setup vs. bare (rung1→4): net +2** — the same two writing tasks; nothing else moved.

**Opus 4.8 spot check (7 runs, targeted):** bare Opus passes `portfolio-writeup` and
`plain-explainer` — the exact two tasks Sonnet needed CLAUDE.md for — so the knowledge
layer's benefit **shrinks as the base model gets stronger**. Opus did *not* crack the two
hard coding tasks (`dashboard-digest`, `pir-workload-feature`) even with skills, same as
Sonnet.

**Sign-test (Sonnet):** rung 4 beat rung 1 on **2 of the 12** tasks (10 ties, 0 losses).
Well under the "≥ a clear majority" bar — the full setup is statistically indistinguishable
from bare on this suite.

**Total API spend this iteration: ~$9.94** (Sonnet $5.95, Opus $3.99), excluding errored/
DNF runs.

---

## Which layers / skills earn their keep

| Layer / skill | Verdict this iteration | Why |
|---------------|------------------------|-----|
| **CLAUDE.md / knowledge routing** | ✅ **Keep** | Only layer with attributable pass/fail lift (+2), ~cheap (does not raise tokens). Its value: your voice + project context on writing tasks. |
| **Memory (behavior)** | ⚠️ **Unproven here** | Net −1 on pass/fail. Its job (behavioral nudging) isn't what pass/fail measures — but it showed no measurable win and adds context. |
| **Curated skills (rung 4)** | ⚠️ **Not justified on this suite** | 0 skill-attributed pass/fail lifts; ~2× the tokens. Every skill-task was already passed bare. |
| `dt-analyze`, `dt-qa`, `dt-review`, `dt-fix`, `dt-ui`, `ai-usage-optimizer`, `baseball-research-advisor` | "both pass — no lift needed" | The bare model already passed these tasks. The checks aren't hard enough to reveal skill value. |
| `dev-team-auto` | **Not tested** | Can't be exercised in a 300s headless one-shot (it orchestrates multi-agent loops for minutes-to-hours). Needs a different harness mode. |

**The two tasks nothing fixes** — `dashboard-digest` (a `<=7` vs `8`-day boundary bug) and
`pir-workload-feature` (using count-based instead of the module's time-based rolling
window) — fail at all four rungs *and* on Opus. These are the genuinely hard cases worth
keeping as a difficulty signal.

---

## What I'd change (prescriptive)

1. **Don't prune memory or skills on this evidence — fix the eval first.** The real finding
   is that **10/12 tasks are too easy**: a setup can only prove its worth on tasks the bare
   model fails. Next iteration, raise task difficulty (multi-file, multi-step, subtle
   correctness) so skills have room to show value.
2. **Add non-pass/fail metrics that can see skill value.** Skills plausibly help via
   *process/quality/token-efficiency*, none of which the current gate captures — and on
   raw tokens they currently *cost* ~2×. Measure turns-to-green, revision count, and a
   blind quality judgment (kept in the quarantined appendix), or the "does the setup help"
   question will keep coming back "no" for the wrong reason.
3. **Weight CLAUDE.md as the proven win.** It's the cheap layer that actually moved
   outcomes; keep it lean and current.
4. **Reconsider what rung 4 is for.** If the skills' value is orchestration on hard,
   multi-step work, the one-shot `claude -p` harness structurally can't show it. Either
   build a multi-turn/worktree harness mode (also needed for `dev-team-auto`) or accept
   that this eval measures the knowledge/memory layers well and the skills poorly.

---

## Caveats (read before acting)

- **1 run per cell.** The rung-3 `portfolio-writeup` regression and both writing flips are
  within single-run noise. Directional, not definitive.
- **Check confidence varies.** Code checks (real vitest/pytest/filesystem/HTML-parse) are
  high-confidence; the writing/analysis checks are grep-based proxies for structure and key
  claims (MODERATE) — good enough to separate a real answer from a vacuous one, not to
  grade nuance.
- **Skills may help in ways this can't see.** Pass/fail ignores quality, process, and
  multi-step orchestration. "No lift" here means "no lift *on single-shot objective
  correctness*," not "no value."
- **`usage-audit` is a deliberate skill-reward task** (flagged, like `pir`). It passed at
  all rungs anyway — the bare model reasons the audit out from the inline data.
- **Opus is a 7-run targeted spot check**, not the full 24-run sweep (chosen for cost);
  `pir` rung-1 timed out on both Sonnet and Opus bare (the hardest task starves a bare
  model) and is recorded as DNF.
- **Harness note:** the OAuth token baked into the per-rung configs expires after ~1 hour,
  so a single iteration must finish inside that window or refresh mid-run (score.py now
  flags check-exit-2 as `infra_error` so an unscoreable run can't masquerade as a failure).

*(Full per-rung, per-skill, and per-run tables below.)*

---


os SHA: `c0c2b45`
runs: 55

## Token & Cost Usage by Rung

| Rung | Avg tokens | Avg cost | Total cost | N runs |
|------|-----------|----------|-----------|--------|
| rung1 | 84,995 | $0.1415 | $2.1220 | 15 |
| rung2 | 63,411 | $0.1021 | $1.2255 | 12 |
| rung3 | 66,390 | $0.1088 | $1.3057 | 12 |
| rung4 | 148,191 | $0.1921 | $3.0741 | 16 |
| **all** | | | **$7.7273** | |

## Pass/Fail by Rung

| Rung | Pass | Fail |
|------|------|------|
| rung1 | 10 | 5 |
| rung2 | 10 | 2 |
| rung3 | 9 | 3 |
| rung4 | 12 | 4 |

## Paired Sign-Test

Action threshold: ≤7 wins on ≥3 tasks = prune candidate

### Model: claude-opus-4-8

**rung1_vs_rung2**: higher rung won n/a (no discriminating tasks)

  - analysis/map-module: missing
  - analysis/qa-failing-test: missing
  - analysis/review-flaw: missing
  - analysis/usage-audit: missing
  - coding/apply-review-fixes: missing
  - coding/dashboard-a11y: missing
  - coding/dashboard-digest: missing
  - coding/launchd-service: missing
  - coding/pir-workload-feature: missing
  - writing/baseball-methodology-critique: missing
  - writing/plain-explainer: missing
  - writing/portfolio-writeup: missing

**rung2_vs_rung3**: higher rung won n/a (no discriminating tasks)

  - analysis/map-module: missing
  - analysis/qa-failing-test: missing
  - analysis/review-flaw: missing
  - analysis/usage-audit: missing
  - coding/apply-review-fixes: missing
  - coding/dashboard-a11y: missing
  - coding/dashboard-digest: missing
  - coding/launchd-service: missing
  - coding/pir-workload-feature: missing
  - writing/baseball-methodology-critique: missing
  - writing/plain-explainer: missing
  - writing/portfolio-writeup: missing

**rung3_vs_rung4**: higher rung won n/a (no discriminating tasks)

  - analysis/map-module: missing
  - analysis/qa-failing-test: missing
  - analysis/review-flaw: missing
  - analysis/usage-audit: missing
  - coding/apply-review-fixes: missing
  - coding/dashboard-a11y: missing
  - coding/dashboard-digest: missing
  - coding/launchd-service: missing
  - coding/pir-workload-feature: missing
  - writing/baseball-methodology-critique: missing
  - writing/plain-explainer: missing
  - writing/portfolio-writeup: missing

**rung1_vs_rung4**: higher rung won n/a (no discriminating tasks)

  - analysis/map-module: missing
  - analysis/qa-failing-test: missing
  - analysis/review-flaw: missing
  - analysis/usage-audit: missing
  - coding/apply-review-fixes: missing
  - coding/dashboard-a11y: missing
  - coding/dashboard-digest: tie
  - coding/launchd-service: missing
  - coding/pir-workload-feature: missing
  - writing/baseball-methodology-critique: missing
  - writing/plain-explainer: tie
  - writing/portfolio-writeup: tie

### Model: claude-sonnet-4-6

**rung1_vs_rung2**: higher rung won 2/2 (ties=10)

  - analysis/map-module: tie
  - analysis/qa-failing-test: tie
  - analysis/review-flaw: tie
  - analysis/usage-audit: tie
  - coding/apply-review-fixes: tie
  - coding/dashboard-a11y: tie
  - coding/dashboard-digest: tie
  - coding/launchd-service: tie
  - coding/pir-workload-feature: tie
  - writing/baseball-methodology-critique: tie
  - writing/plain-explainer: rung2 wins
  - writing/portfolio-writeup: rung2 wins

**rung2_vs_rung3**: higher rung won 0/1 (ties=11)

  - analysis/map-module: tie
  - analysis/qa-failing-test: tie
  - analysis/review-flaw: tie
  - analysis/usage-audit: tie
  - coding/apply-review-fixes: tie
  - coding/dashboard-a11y: tie
  - coding/dashboard-digest: tie
  - coding/launchd-service: tie
  - coding/pir-workload-feature: tie
  - writing/baseball-methodology-critique: tie
  - writing/plain-explainer: tie
  - writing/portfolio-writeup: rung2 wins

**rung3_vs_rung4**: higher rung won 1/1 (ties=11)

  - analysis/map-module: tie
  - analysis/qa-failing-test: tie
  - analysis/review-flaw: tie
  - analysis/usage-audit: tie
  - coding/apply-review-fixes: tie
  - coding/dashboard-a11y: tie
  - coding/dashboard-digest: tie
  - coding/launchd-service: tie
  - coding/pir-workload-feature: tie
  - writing/baseball-methodology-critique: tie
  - writing/plain-explainer: tie
  - writing/portfolio-writeup: rung4 wins

**rung1_vs_rung4**: higher rung won 2/2 (ties=10)

  - analysis/map-module: tie
  - analysis/qa-failing-test: tie
  - analysis/review-flaw: tie
  - analysis/usage-audit: tie
  - coding/apply-review-fixes: tie
  - coding/dashboard-a11y: tie
  - coding/dashboard-digest: tie
  - coding/launchd-service: tie
  - coding/pir-workload-feature: tie
  - writing/baseball-methodology-critique: tie
  - writing/plain-explainer: rung4 wins
  - writing/portfolio-writeup: rung4 wins

## Verdict — does the setup earn its keep?

### Model: claude-opus-4-8

**Pass rate by rung:**

- rung1: 2/3 passed
- rung4: 2/4 passed

**What each added layer bought (fail→pass flips on the next rung):**

- **full setup vs. bare** (rung1→4): +0 / −0 = net +0

**Per-task pass matrix:**

| Task | Skill | r1 | r4 |
|------|-------|---|---|
| analysis/map-module | dt-analyze | · | · |
| analysis/qa-failing-test | dt-qa | · | · |
| analysis/review-flaw | dt-review | · | · |
| analysis/usage-audit | ai-usage-optimizer | · | · |
| coding/apply-review-fixes | dt-fix | · | · |
| coding/dashboard-a11y | dt-ui | · | · |
| coding/dashboard-digest | — | ✗ | ✗ |
| coding/launchd-service | — | · | · |
| coding/pir-workload-feature | — | · | ✗ |
| writing/baseball-methodology-critique | baseball-research-advisor | · | · |
| writing/plain-explainer | none | ✓ | ✓ |
| writing/portfolio-writeup | none | ✓ | ✓ |

### Model: claude-sonnet-4-6

**Pass rate by rung:**

- rung1: 8/12 passed
- rung2: 10/12 passed
- rung3: 9/12 passed
- rung4: 10/12 passed

**What each added layer bought (fail→pass flips on the next rung):**

- **CLAUDE.md / knowledge routing** (rung1→2): +2 / −0 = net +2 (writing/plain-explainer, writing/portfolio-writeup)
- **memory (behavior instructions)** (rung2→3): +0 / −1 = net -1
- **curated skills** (rung3→4): +1 / −0 = net +1 (writing/portfolio-writeup)
- **full setup vs. bare** (rung1→4): +2 / −0 = net +2 (writing/plain-explainer, writing/portfolio-writeup)

**Per-skill lift (rung3→rung4 — did the specific skill earn its keep?):**

| Task | Curated skill | rung3 | rung4 | Verdict |
|------|---------------|-------|-------|---------|
| analysis/map-module | dt-analyze | ✓ | ✓ | both pass (no lift needed) |
| analysis/qa-failing-test | dt-qa | ✓ | ✓ | both pass (no lift needed) |
| analysis/review-flaw | dt-review | ✓ | ✓ | both pass (no lift needed) |
| analysis/usage-audit | ai-usage-optimizer | ✓ | ✓ | both pass (no lift needed) |
| coding/apply-review-fixes | dt-fix | ✓ | ✓ | both pass (no lift needed) |
| coding/dashboard-a11y | dt-ui | ✓ | ✓ | both pass (no lift needed) |
| coding/dashboard-digest | — | ✗ | ✗ | both fail — skill did not help |
| coding/launchd-service | — | ✓ | ✓ | both pass (no lift needed) |
| coding/pir-workload-feature | — | ✗ | ✗ | both fail — skill did not help |
| writing/baseball-methodology-critique | baseball-research-advisor | ✓ | ✓ | both pass (no lift needed) |
| writing/plain-explainer | none | ✓ | ✓ | both pass (no lift needed) |
| writing/portfolio-writeup | none | ✗ | ✓ | skill WON |

Skills that flipped a task fail→pass at rung4: `none` (writing/portfolio-writeup).

**Per-task pass matrix:**

| Task | Skill | r1 | r2 | r3 | r4 |
|------|-------|---|---|---|---|
| analysis/map-module | dt-analyze | ✓ | ✓ | ✓ | ✓ |
| analysis/qa-failing-test | dt-qa | ✓ | ✓ | ✓ | ✓ |
| analysis/review-flaw | dt-review | ✓ | ✓ | ✓ | ✓ |
| analysis/usage-audit | ai-usage-optimizer | ✓ | ✓ | ✓ | ✓ |
| coding/apply-review-fixes | dt-fix | ✓ | ✓ | ✓ | ✓ |
| coding/dashboard-a11y | dt-ui | ✓ | ✓ | ✓ | ✓ |
| coding/dashboard-digest | — | ✗ | ✗ | ✗ | ✗ |
| coding/launchd-service | — | ✓ | ✓ | ✓ | ✓ |
| coding/pir-workload-feature | — | ✗ | ✗ | ✗ | ✗ |
| writing/baseball-methodology-critique | baseball-research-advisor | ✓ | ✓ | ✓ | ✓ |
| writing/plain-explainer | none | ✗ | ✓ | ✓ | ✓ |
| writing/portfolio-writeup | none | ✗ | ✓ | ✗ | ✓ |

## Per-Run Results

| Task | Rung | Pass | Tokens | Cost |
|------|------|------|--------|------|
| analysis/map-module | rung1 | ✓ | 25,987 | $0.0814 |
| analysis/map-module | rung2 | ✓ | 45,842 | $0.1049 |
| analysis/map-module | rung3 | ✓ | 55,073 | $0.1209 |
| analysis/map-module | rung4 | ✓ | 80,958 | $0.0922 |
| analysis/qa-failing-test | rung1 | ✓ | 43,281 | $0.1264 |
| analysis/qa-failing-test | rung2 | ✓ | 37,396 | $0.0996 |
| analysis/qa-failing-test | rung3 | ✓ | 57,405 | $0.1277 |
| analysis/qa-failing-test | rung4 | ✓ | 134,435 | $0.1141 |
| analysis/review-flaw | rung1 | ✓ | 4,135 | $0.0361 |
| analysis/review-flaw | rung2 | ✓ | 5,466 | $0.0364 |
| analysis/review-flaw | rung3 | ✓ | 8,941 | $0.0488 |
| analysis/review-flaw | rung4 | ✓ | 26,655 | $0.0599 |
| analysis/usage-audit | rung1 | ✓ | 3,776 | $0.0292 |
| analysis/usage-audit | rung2 | ✓ | 5,333 | $0.0329 |
| analysis/usage-audit | rung3 | ✓ | 8,981 | $0.0480 |
| analysis/usage-audit | rung4 | ✓ | 123,359 | $0.1508 |
| coding/apply-review-fixes | rung1 | ✓ | 11,432 | $0.0260 |
| coding/apply-review-fixes | rung2 | ✓ | 13,276 | $0.0295 |
| coding/apply-review-fixes | rung3 | ✓ | 23,819 | $0.0444 |
| coding/apply-review-fixes | rung4 | ✓ | 77,753 | $0.0692 |
| coding/dashboard-a11y | rung1 | ✓ | 32,339 | $0.0630 |
| coding/dashboard-a11y | rung2 | ✓ | 19,404 | $0.0418 |
| coding/dashboard-a11y | rung3 | ✓ | 24,275 | $0.0508 |
| coding/dashboard-a11y | rung4 | ✓ | 105,418 | $0.0899 |
| coding/dashboard-digest | rung1 | ✗ | 441,564 | $0.4712 |
| coding/dashboard-digest | rung2 | ✗ | 385,916 | $0.3717 |
| coding/dashboard-digest | rung3 | ✗ | 320,628 | $0.3330 |
| coding/dashboard-digest | rung4 | ✗ | 444,115 | $0.3500 |
| coding/launchd-service | rung1 | ✓ | 26,469 | $0.0755 |
| coding/launchd-service | rung2 | ✓ | 73,001 | $0.1007 |
| coding/launchd-service | rung3 | ✓ | 92,146 | $0.1050 |
| coding/launchd-service | rung4 | ✓ | 302,603 | $0.1790 |
| coding/pir-workload-feature | rung2 | ✗ | 108,232 | $0.2575 |
| coding/pir-workload-feature | rung3 | ✗ | 114,132 | $0.2333 |
| coding/pir-workload-feature | rung4 | ✗ | 208,062 | $0.2965 |
| writing/baseball-methodology-critique | rung1 | ✓ | 3,931 | $0.0345 |
| writing/baseball-methodology-critique | rung2 | ✓ | 5,147 | $0.0330 |
| writing/baseball-methodology-critique | rung3 | ✓ | 9,185 | $0.0540 |
| writing/baseball-methodology-critique | rung4 | ✓ | 54,012 | $0.0923 |
| writing/plain-explainer | rung1 | ✗ | 2,300 | $0.0115 |
| writing/plain-explainer | rung2 | ✓ | 4,012 | $0.0175 |
| writing/plain-explainer | rung3 | ✓ | 7,507 | $0.0303 |
| writing/plain-explainer | rung4 | ✓ | 25,525 | $0.0459 |
| writing/portfolio-writeup | rung1 | ✗ | 39,273 | $0.0771 |
| writing/portfolio-writeup | rung2 | ✓ | 57,909 | $0.1000 |
| writing/portfolio-writeup | rung3 | ✗ | 74,588 | $0.1095 |
| writing/portfolio-writeup | rung4 | ✓ | 63,489 | $0.1112 |
| coding/pir-workload-feature | rung1 | ✗ | 220,659 | $0.3590 |
| coding/dashboard-digest | rung4 | ✗ | 507,626 | $0.6350 |
| coding/pir-workload-feature | rung4 | ✗ | 133,528 | $0.5221 |
| coding/dashboard-digest | rung1 | ✗ | 410,396 | $0.6596 |
| writing/portfolio-writeup | rung1 | ✓ | 6,595 | $0.0468 |
| writing/portfolio-writeup | rung4 | ✓ | 59,870 | $0.1895 |
| writing/plain-explainer | rung1 | ✓ | 2,794 | $0.0248 |
| writing/plain-explainer | rung4 | ✓ | 23,646 | $0.0765 |

