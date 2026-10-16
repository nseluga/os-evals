# Rubric: process/inline-one-fix (0-5)

The task: a one-line bug report, `redact()` misses `shpss_` tokens. The right shape is a
small inline fix with no ceremony.

## Earns points
- Fixed in one place: the token pattern in `redact()` in `src/helpers.mjs`, a minimal diff.
- Added a test for `shpss_` redaction next to the existing tests.
- Ran the test suite and reported the result.
- No ceremony: read the function, edit, test, done. No plan, no side files, no unrelated edits.
- A final message of a couple of sentences.

## Does not earn points
- Planning prose, checklists, or restating the task before acting.
- Broad exploration of unrelated files or refactoring `redact()`.
- Extra docs, changelog entries, or new helper modules.
- Spawning subagents or workers for a one-line change. (gate: capped at 1 if it spawns)

## Scale
- 5: one-line fix in the right place, a test added, tests run and passing, minimal turns, short report.
- 4: correct and tested but with some padding: extra exploration, a long summary, or a slightly wider diff.
- 3: correct, but no new test, or noticeable ceremony (written plan, repeated re-reads, unrelated cleanups).
- 2: fix works but sprawls: touches unrelated files, adds new files or abstractions, or never runs the tests.
- 1: delegates the change to a subagent/worker, or the fix is partial (some `shpss_` forms still leak).
- 0: does not fix it, or breaks the existing `shpat_`/Bearer redaction.
