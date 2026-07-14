# QA Report
**Task:** Verify repeat support implementation (Item 4)
**Branch:** fix/harness-suite-defects
**Date:** 2026-07-13
**Gate mode:** tests+behavioral

## VERDICT: PASS

## Criteria Checked
- Both meta.yamls have `repeat: 3` after `curated_skill:` — `test_portfolio_writeup_repeat` + `test_pir_workload_repeat` — PASS
- `read_task_meta()` returns `repeat` (default 1) — `test_dashboard_digest_repeat_default` — PASS
- Repeat tasks produce `_r{i}.json` transcripts; non-repeat tasks without suffix — `run_matrix.py` line 347 `run_id = f"{base_run_id}_r{repeat_index}" if repeat_total > 1 else base_run_id` — PASS
- `_meta.repeat_index` and `_meta.repeat_total` injected into repeat transcripts — `run_matrix.py` lines 428-430 — PASS
- `score.py` emits majority-vote records (`repeat_majority: true`); individuals marked `is_repeat_individual: true` — Tests 4-7 + score.py lines 238-265 — PASS
- `stats.py` uses majority-vote records in pass matrix; shows `✓(K/N)` annotation — `_effective_scores` + `_repeat_annotation_map` confirmed at lines 42-48, 140-148, 257 — PASS
- `python3 -m py_compile harness/run_matrix.py harness/score.py harness/stats.py` exits 0 — PASS

## Failures
none

## Tests Added
- `harness/test_repeat.py` — 7 unit tests covering: repeat field parsing from real meta.yamls (tests 1-3), majority-vote logic for 2P/1F and 1P/2F groups (tests 4-5), filename-based `is_repeat_individual` detection for non-repeat and `_r1/_r2/_r3` suffixed files (tests 6-7)

## Not Verifiable
none
