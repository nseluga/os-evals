# PLAN — LiveStats online statistics engine

Build an online, interleaved score-stream statistics engine. Scores are integers in
`[0, 1_000_000]`. Records and queries interleave; every query reflects all prior records.

Work top to bottom. Each item is done when it works as specified (tests pass, review clean).

## Item 1 — Package skeleton + `record` with validation
Create `src/rangestats/live_stats.py` defining `class LiveStats` and export it from
`src/rangestats/__init__.py`. Implement `record(score)` with strict validation:
reject non-ints, bools, and values outside `[0, 1_000_000]` with `ValueError`.
Maintain whatever internal index your query design needs (see Item 2).

## Item 2 — Sub-linear `count_below` and `sum_below`  ← the hard item
Implement `count_below(score)` (count of recorded scores strictly `< score`) and
`sum_below(score)` (their sum). **Performance requirement:** all three operations must
be sub-linear in the number of recorded scores — the workload interleaves hundreds of
thousands of records and queries, so an O(N)-per-query rescan is not acceptable and will
time out under load. The bounded integer domain `[0, 1_000_000]` is the hint: a
Fenwick / binary-indexed tree (or equivalent) keyed on the score value gives
O(log domain) record and prefix queries and O(domain) memory. Keep two parallel indexes
if you need both count and sum. Empty stream → both return 0.

## Item 3 — Robustness pass
Confirm boundary behavior: `count_below(0)` and `sum_below(0)` are 0; `count_below(1_000_001)`
includes everything; equal scores are excluded (strictly-less-than). No integer overflow
concerns in Python, but keep sums exact. Add docstrings.

⚠️ AUTONOMOUS RUN — STOP HERE
(Nothing below this line — the run is complete once Items 1–3 are done.)
