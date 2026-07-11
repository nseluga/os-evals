You are working in a git repository for an analytics service. Read `PLAN.md` and drive
it to completion — implement every item in order.

The deliverable is an online statistics engine `LiveStats` for a high-throughput score
stream. Records and queries are **interleaved** (each query must reflect every record
seen so far), so you cannot batch or pre-sort the input.

Implement `LiveStats` in `src/rangestats/live_stats.py` (a class), exported from the
package. Scores are integers in the closed range `[0, 1_000_000]`.

API:

```python
class LiveStats:
    def __init__(self) -> None: ...
    def record(self, score: int) -> None:
        """Ingest one score. Raises ValueError if score is not an int in [0, 1_000_000]."""
    def count_below(self, score: int) -> int:
        """How many recorded scores are STRICTLY LESS THAN `score`."""
    def sum_below(self, score: int) -> int:
        """Sum of all recorded scores STRICTLY LESS THAN `score`."""
```

Correctness rules:
- `count_below`/`sum_below` consider only scores recorded so far, strictly `< score`.
- On an empty stream both return `0`.
- `record` validates input: a non-int, a bool, or a value outside `[0, 1_000_000]`
  raises `ValueError` (do NOT silently clamp or drop).

**This is the crux, and PLAN.md item 2 is explicit about it:** the engine must stay fast
as the stream grows. A design that rescans all recorded scores on every query is
O(N) per query and collapses to O(N²) over a run — it will NOT meet the performance
bound the tests enforce on a large interleaved workload. Choose a data structure whose
`record`/`count_below`/`sum_below` are all sub-linear in the number of recorded scores
(the bounded integer domain makes this possible). Keep it standard-library only — no
third-party packages.
