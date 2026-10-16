# Rubric: map of a data-loading pipeline

The author was asked to read the `src/lib/` module of an Astro + TypeScript project dashboard and write a concise map for a new contributor: the entry point that returns the fully merged list of projects, each stage by file and function name from raw source to merged result, where the two data sources live (per-project source of truth vs. manual overrides) and how they are combined, and any concurrency or correctness seam worth knowing before editing. No code was to be changed.

Judge only the artifact. Reward a map a new contributor could navigate by; do not reward length or formatting.

## Scale
- 5: Names the entry point (`getMergedProjects`) and every stage in order by file and function (`getProjects`, `readManual`, the merge step); states what each source contains and how overrides are applied (including any whitelist); names the concurrency seam (a mutex guarding manual writes) and says why it matters before editing. Accurate, no invented symbols, readable top to bottom.
- 4: Entry point, both upstream stages and the merge step are named correctly and the combination is explained; one seam is named. May omit file paths, or the reason a seam matters, or one secondary detail.
- 3: Entry point and at least one upstream stage are named correctly and the flow is roughly right, but a stage, the combination rule, or every seam is missing or only vaguely described.
- 2: Mostly generic description of "reads data and combines it"; at most one real symbol; no seam.
- 1: Almost no concrete symbols or files; could describe any project.
- 0: Empty, off-topic, or describes code changes instead of mapping.

## Does not earn points
- Generic statements ("it loads projects and merges them") with no function or file names.
- Symbols, files or behaviour that are not in the module (invented detail), however plausible.
- Padding: restating the prompt, architecture boilerplate, advice about Astro in general.
- Proposing refactors or edits; the deliverable is a map.
