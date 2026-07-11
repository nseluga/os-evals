Below is a snapshot of a developer's AI setup and how they actually used it over the
last 20 Claude Code sessions. Audit it and answer two questions in plain English:

1. **Which subsystem is most under-used relative to the work being done, and what should
   change?** Point to the evidence.
2. **Which model tier (Opus / Sonnet / Haiku) should they use for a large, multi-file
   refactor that requires reasoning across modules — and why?**

## Installed skills (personal)
- `dev-team`, `dev-team-auto`, `dt-engineer`, `dt-qa`, `dt-review`, `dt-fix`, `dt-analyze`,
  `dt-ui` — a coordinated multi-agent "dev team" for building/testing/reviewing code.
- `baseball-research-advisor` — skeptical analytics peer review.
- `ai-usage-optimizer` — audits how well the other systems are being used.

## Memory (behavior preferences)
- "Surface tradeoffs proactively with any recommendation."
- "For mechanical/read-only work use a cheap model; reasoning roles need Sonnet or better."

## Usage log (last 20 sessions), by task type and how it was handled
| Sessions | Task type                                   | How it was handled            |
|----------|---------------------------------------------|-------------------------------|
| 9        | Multi-file feature builds (3+ files each)   | single ad-hoc chat, no agents |
| 4        | Multi-file refactors across modules         | single ad-hoc chat, no agents |
| 3        | Bug fixes with tests                        | single ad-hoc chat, no agents |
| 2        | Baseball analytics methodology questions    | `baseball-research-advisor`   |
| 2        | Portfolio/writing                           | single ad-hoc chat            |

Across all 20 sessions the `dev-team` / `dt-*` skills were invoked **0 times**, despite
16 of 20 sessions being multi-file build/refactor/test work those skills are built for.
