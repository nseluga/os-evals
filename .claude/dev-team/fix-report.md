# Fix Report
**Date:** 2026-07-13
**Findings addressed:** 4 of 4 total: 0 QA failures + 4 review findings

## Changes Made
- `harness/score.py:91` — added `if line[:1] in (" ", "\t"): continue` before key-matching loop to skip indented description prose — review Important 1
- `harness/stats.py:338-340` — extracted `rung1_scores` filter before table render; if empty, emits `_no rung-1 data for this anchor_` and returns early — review Important 2
- `harness/stats.py:356` — replaced `data['run_count']` with `len(scored)` (plus `+N anchors` note when anchors present) for consistent header count — review Minor 1
- `harness/stats.py:432-433` — hoisted sentinel filter to `scored` in `main()`, passing pre-filtered list to `compute_stats` and `token_summary` instead of full `scores` — review Minor 2

## Disputed
None.

## Deferred
None.
