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

## Still needs a task authored (next session picks up here)

The task cases for these curated skills are NOT yet written. Each needs a frozen
workspace + an objective check that specifically stresses that skill's job:

| Curated skill | Task idea (starting point — not final) | Likely batch |
|---------------|----------------------------------------|--------------|
| `ai-usage-optimizer` | Given a (frozen) snapshot of skills/memory/usage, produce a correct "which subsystem is under-used / which model for task X" audit; check against an authored answer key. | analysis |
| `dev-team-auto` | Autonomous PLAN.md → drive multiple items to completion unattended; check that each item's authored gate passes + PROGRESS.md updated. | coding |
| `dt-analyze` | Map an unfamiliar multi-file module before a change; check that the produced map names the right seams/entry points (assertion checklist). | coding/analysis |
| `dt-qa` | Given an implementation with a planted bug, author tests that catch it; check that the emitted tests fail on the bug and pass on the fix. | coding |
| `dt-review` | Given code with a known efficiency/scalability/security flaw, produce a review that flags it; check the report names the real issue. | coding/analysis |
| `dt-fix` | Given a review report + code, apply the fixes; check the cited issues are resolved and behavior preserved. | coding |
| `dt-ui` | Frontend task (layout/hierarchy/a11y) with an objective check (e.g. axe assertions, DOM/structure checks). | coding |

Coverage so far: 3/10 curated skills have a validated task (`baseball-research-advisor`,
`dt-engineer`, `dev-team`). 7 curated skills still need a task authored.

STOP POINT: per this session's scope, the remaining analysis/writing task cases were
intentionally NOT authored. This table is the clean handoff for writing them.
