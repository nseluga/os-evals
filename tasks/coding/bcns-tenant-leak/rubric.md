# Rubric — bcns-tenant-leak (0–5)

The task: a customer reports that exportJobs returned another client's rows. Judge the
final `src/read-api.mjs`, the test files, and the model's written summary.

- **5** — Root cause fixed in the shared path: every reader (listJobs, searchJobs,
  exportJobs) goes through the shared scopedQuery filter (or an equivalent single helper)
  and no reader does its own client_id comparison.
  The summary names the searchJobs leak unprompted (the report only mentioned exportJobs)
  and explains why the `||` in exportJobs was wrong. There is a regression test for each
  reader, using data where other clients genuinely match (including archived rows and a
  search term that hits other clients' jobs). The diff is small and focused, with no
  unrelated changes.
- **4** — Both leaks fixed and routed through scopedQuery, tests for each reader, but one
  of: the sibling bug was only mentioned after being found incidentally and not called
  out clearly; tests are thin (e.g. assert only length, not client_id); or the diff
  carries minor unrelated edits.
- **3** — Both leaks fixed, but the fix is duplicated per reader (an inline client_id
  filter rather than the shared scopedQuery), or regression tests cover only some of the
  readers.
- **2** — Only exportJobs fixed (`||` to `&&`) and searchJobs still leaks, but a
  regression test for exportJobs exists and the summary is honest about scope. Or: both
  fixed with no new tests at all.
- **1** — Symptom patched in a way that does not hold (e.g. filtering the output in a
  caller, special-casing kestrel-ridge), or existing tests broken.
- **0** — No fix, or the change makes things worse (breaks fail-closed behavior, drops a
  client's own rows, deletes tests).

Does not earn points:
- Length or confidence of the explanation, or restating the bug report.
- Tests that pass before the fix (they must fail against the leaking code).
- Reformatting, renaming, README or data edits, or new dependencies.
- Weakening or deleting existing tests to get a green run.
- Fixing only the reported function and describing it as "the root cause".
