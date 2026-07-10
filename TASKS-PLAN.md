# Task → Skill Map (rung-4 curated skills)

Rung 4 loads only the skills I actually reach for (see SPEC.md, arm 4). To make the
suite legible, every task is slotted against the ONE curated skill it is meant to
exercise — so a rung3→rung4 lift on that task is evidence for *that* skill, not
"skills in general."

Curated rung-4 skills (10): `ai-usage-optimizer`, `dev-team`, `dev-team-auto`,
`baseball-research-advisor`, `dt-analyze`, `dt-engineer`, `dt-qa`, `dt-review`,
`dt-fix`, `dt-ui`.

## Coding batch (authored + validated)

| Task | Curated skill exercised | Why this skill / what the task probes | Status |
|------|-------------------------|----------------------------------------|--------|
| `coding/pir-workload-feature` | `baseball-research-advisor` | ACWR feature needs the domain semantics (acute÷chronic, exclude current appearance) the baseball skill supplies; property-based check rewards that reasoning, not memorized constants. | ✅ authored + validated |
| `coding/dashboard-digest` | `dt-engineer` | Clean "implement `computeDigestBuckets` from a spec with boundary cases" — the core Engineer build-to-spec loop; pure vendored unit test gates it. | ✅ authored + validated |
| `coding/launchd-service` | `dev-team` / `dt-engineer` | Multi-file infra task (plist + install/uninstall scripts) with a non-obvious constraint (launchd's minimal PATH → no `npm`); filesystem-assertion check. Fits the general dev-team build loop. | ✅ authored + validated |

Note: the coding batch leans on `dt-engineer` / `dev-team` because that's what coding
tasks naturally exercise. The remaining dev-team specialist skills (`dt-analyze`,
`dt-qa`, `dt-review`, `dt-fix`, `dt-ui`) and the meta/auto skills need purpose-built
tasks — see below.

## Analysis batch (authored + validated)

| Task | Curated skill | What it probes | Status |
|------|---------------|----------------|--------|
| `analysis/map-module` | `dt-analyze` | Map the real project-dashboard merge pipeline (read-only git workspace); check names the entry point, both stages, merge step, and mutex seam. | ✅ authored + validated |
| `analysis/review-flaw` | `dt-review` | Flawed module inline (SQL injection, hardcoded secret, O(n·m) join); check the review names the injection + ≥1 more. | ✅ authored + validated |
| `analysis/usage-audit` | `ai-usage-optimizer` | Snapshot of skills/memory/usage log; check names dev-team as under-used + picks a reasoning-grade model. ⚠️ deliberate skill-reward (flagged, like pir). | ✅ authored + validated |
| `analysis/qa-failing-test` | `dt-qa` | Seed a contract-violating `apply_discount`; model writes a test; check it DISCRIMINATES (fails buggy, passes fixed). | ✅ authored + validated |

## Writing batch (authored + validated)

| Task | Curated skill / layer | What it probes | Status |
|------|-----------------------|----------------|--------|
| `writing/baseball-methodology-critique` | `baseball-research-advisor` | Flawed eval methodology inline; check names ≥2 of {random-split leakage, same-season label leakage, accuracy-on-imbalance}. | ✅ authored + validated |
| `writing/portfolio-writeup` | knowledge routing + memory style | Portfolio blurb; check: short, no marketing buzzwords, ≥2 concrete specifics. Tests rung 2/3, not a skill. | ✅ authored + validated |
| `writing/plain-explainer` | memory behavior (rung 3) | Explain a hook + recommend; check: plain early definition + a surfaced tradeoff. Tests the two memory behavior facts. | ✅ authored + validated |

## Coding batch — 4th task added

| `coding/apply-review-fixes` | `dt-fix` | Seed handler.py + REVIEW.md (hardcoded secret, eval(), no timeout); check all three fixes applied + behavior preserved. | ✅ |
| `coding/dashboard-a11y` | `dt-ui` | Seed index.html with a11y violations; check via stdlib HTML parser (alt text, control names, labels, real click targets). | ✅ |

## Coverage

**9 of 10 curated skills now have a validated task:** `baseball-research-advisor` (×2),
`dt-engineer`, `dev-team`, `dt-analyze`, `dt-review`, `ai-usage-optimizer`, `dt-qa`,
`dt-fix`, `dt-ui`.

**Not covered — `dev-team-auto` (deferred, with reason):** it orchestrates multiple
sub-agent convergence loops across a whole PLAN.md and spawns worktrees — minutes-to-hours
of unattended work. A headless `claude -p` one-shot with a 300s timeout cannot exercise it
faithfully, and a shrunk "2-item PLAN" would test a stub, not the skill. Authoring it well
needs a different harness mode (long-running, worktree-aware) — out of scope for the
one-shot matrix. Flagged here rather than faked.

Category balance ended at coding=5, analysis=4, writing=3 (12 total) — a mild deviation
from the 4/4/4 ideal, driven by which curated skills are coding- vs. text-shaped. The
scorecard groups by task and by skill, so the imbalance doesn't distort the verdict.

## Harness extensions this batch added (additive, backward-compatible)
- `run_matrix.py`: tasks may ship a `seed/` dir (copied into the per-run workspace) so
  self-contained analysis/writing tasks need no throwaway repo commit; and EVERY run now
  gets its own isolated per-run dir as cwd (empty for pure-text tasks) — a leak guard so a
  text task never reads the eval repo itself.
- `score.py`: attaches `curated_skill` / `category` / `contaminated` / `group` from each
  task's meta.yaml to its score record.
- `stats.py`: cost-per-rung, and a plain-English **Verdict** section (layer-transition
  net wins, per-skill rung3→rung4 lift, per-task pass matrix).
