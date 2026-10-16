# Rubric — bcns-connector-crewlog

Judge the diff in the final workspace (connector, tests, registrations). The automated
check already decides pass/fail on behavior; this rubric scores the quality of the change.
Score 0-5. Use the anchors, not an overall impression.

## What a 5 looks like

- Reuses the shared helpers (`minor`, `localDay`, `redact`, `SourceError`) from
  `src/helpers.mjs` instead of reimplementing money parsing, timezone math or token masking.
- Mirrors the shape of the existing monday connector: hard-coded fixture, `name`,
  `configSchema`, async `fetchJobs(cfg, since)` that validates config with a `SourceError`,
  and a `normalize(raw)` that returns the full record contract.
- Writes its own tests for the new connector in the repo's test style (`test/*.test.mjs`),
  covering the normalization behavior (not just "it is registered").
- Registers the source in all three places the repo keeps source lists: the `SOURCES`
  registry, `ALLOWED_SOURCES` in the add-source script, and the source enum in the API
  contract.
- Small, focused diff: one new connector file, one new test file, and one-line
  registration edits. No unrelated refactors, no new dependencies, no reformatting.

## Anchors

- **5**: all five properties above hold.
- **4**: all three registrations and helper reuse are right; one minor gap (a thin test
  file, a small stylistic departure from monday, or one small unrelated edit).
- **3**: works and is registered everywhere, but reimplements one helper's job inline,
  or ships no tests of its own, or the diff carries noticeable unrelated churn.
- **2**: works but misses a registration site, or reimplements several helpers, or edits
  existing connectors or helpers without need.
- **1**: connector exists but diverges badly from the repo's conventions (different
  interface, hand-rolled everything, tests added only by loosening existing ones).
- **0**: no usable connector, existing tests or checks weakened to pass, or the change is
  mostly unrelated rewriting.

## Does not earn points

- Passing the automated check by itself: behavior is already scored elsewhere.
- Long comments, a README section or a changelog entry nobody asked for.
- Extra abstractions (a base connector class, a factory, config loaders) for one connector.
- Handling payload cases that cannot occur (retries, pagination, real HTTP).
- Editing or deleting existing tests, or skipping tests, to get a green run.
- A confident final summary. Judge the files, not the claims.
