# Review Report
**Date:** 2026-07-13
**Files Reviewed:** 5 (harness/run_matrix.py, harness/score.py, harness/stats.py, tasks/writing/portfolio-writeup/meta.yaml, tasks/coding/pir-workload-feature/meta.yaml)
**Standards Applied:** efficiency, reliability, scalability, fault tolerance

## Summary
The repeat implementation is fundamentally sound: workspace isolation per repeat run is correct, backward compatibility for non-repeat transcripts is clean, and cost aggregation handles None values safely. Two reliability gaps exist: a partial repeat group (e.g., only 1 of 3 transcripts on disk when score.py runs mid-run) produces a premature majority record with misleading `repeat_total`, and `cross_model_section` in stats.py passes unfiltered `all_scores` to `_cell_pass`, allowing individual repeat records to overwrite the majority record in the dict comprehension via last-write-wins semantics.

## Findings

### Important

- `score.py:244–265` — Reliability / Don't Assume Success — partial repeat groups (n < expected repeat_total) emit a majority record with `repeat_total=n` rather than the expected count; a 1-of-3 group produces `repeat_total=1` and a spurious majority-passed=True on 1/1, not 2/3, making the record indistinguishable from a genuine complete majority — fix: gate majority emission on `n >= math.ceil(expected_total / 2)` or at minimum `n == expected_total`, using `template.get("repeat_total")` as the expected total.

- `stats.py:289,313` — Reliability / Handle Errors at Boundaries — `cross_model_section` receives `all_scores` (line 439) and locally drops only sentinels, never calling `_effective_scores`; `_cell_pass` then iterates the unfiltered list and a task with repeat runs has multiple records per (task, rung, model), with the last dict-comprehension write (an individual `_rN` record) silently overwriting the majority record — fix: apply `_effective_scores` in `cross_model_section` before filtering sentinels.

### Minor

- `score.py:252–256` — Reliability / Log with Context — majority record inherits `check_output` and `check_rc` from the template (group[0]), so a majority-PASS record can carry `check_output` from a failing individual run, and vice versa — fix: set `check_output` to a synthesized string like `f"{pass_count}/{n} passed"` and `check_rc` to 0 if majority_passed else 1.

- `score.py:262` — Reliability / Explicit Over Implicit — `repeat_total` in the majority record is set to `n` (number of records found), not the declared `repeat_total` from `_meta`; when partial groups are promoted, this makes the record appear complete — fix: carry `template.get("repeat_total") or n` as `expected_repeat_total` and use `n` only as the observed count.

## STANDARDS.md Updates

- **Repeat-group majority gate**: majority records are only emitted when the observed group size `n` equals (or exceeds the threshold of) the declared `repeat_total`; partial groups remain as orphaned individuals and surface as "missing" in the verdict matrix rather than as premature majorities.
- **Effective-scores discipline**: every stats.py aggregation or display path that iterates scores must go through `_effective_scores()` before any sentinel filter; `cross_model_section` is the canonical negative example.
- **Exit code convention**: `check_rc` 0 = pass, 1 = task fail, 2 = infra/unscoreable; majority records synthesize `check_rc` from the vote outcome rather than inheriting from the template.
