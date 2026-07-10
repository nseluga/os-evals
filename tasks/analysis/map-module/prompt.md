This is an Astro + TypeScript project dashboard. Before anyone changes how projects are
loaded, map the **project data pipeline** in `src/lib/` so a new contributor understands
it.

Read the relevant files and produce a concise map that covers:
- The **entry point** a caller uses to get the fully-merged list of projects.
- Each stage the data flows through, by **file and function name**, from raw source to
  the final merged result.
- Where the two data sources are (the per-project source of truth vs. the manual
  overrides), and how they are combined.
- Any concurrency or correctness seam worth knowing about before editing.

Do not change any code. The deliverable is the map.
